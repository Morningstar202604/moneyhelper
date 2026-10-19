"""LLM 派工（M3.2）：让模型把老板一句话拆成工单，而不是关键词匹配。

## 为什么值得用模型

规则派工只能匹配预设关键词：
- "帮我看看这季度是不是该调整一下了" → 命中不了任何规则，只能兜底派两个部门
- "先把上个月的账对一遍，再看看有没有该赎回的" → 规则只认出"账"，
  漏掉"赎回"背后的投资部

模型的强项正是这种语义组合。但模型输出不可信，所以：

## 三道防线

1. **schema 约束**：要求模型输出 `{"orders":[{"dept","task","tools_allowed","budget_tokens"}]}`，
   用 `DispatchPlan.model_validate` 卡一遍。部门名必须是四个之一，
   同部门不能重复，任务不能空白——不合法直接判失败。
2. **工具白名单收窄**：模型只能从该部门的合法工具里选，
   自己编造的工具名会被剔除（不是信任模型写的 `tools_allowed`）。
3. **失败降级**：模型不可用、超时、输出非法 → 一律回落到规则派工。
   派工是入口，不能因为模型抖动就让整个部门模式不可用。

## token 预算

模型可以为每个工单设 `budget_tokens`，但会被夹到
`MIN_BUDGET..MAX_BUDGET` 区间：给太少部门跑不完，给太多会挤占其他部门。
"""

from __future__ import annotations

import json

from . import llm
from .dept_models import DEPARTMENTS, DEPT_TITLES, DispatchPlan, WorkOrder
from .logging_utils import get_logger

log = get_logger(__name__)

# 预算夹逼区间：低于 500 一个部门连一次工具调用都跑不完；
# 高于 8000 单部门会挤占整轮预算（默认总预算按 4000×部门数估算）。
MIN_BUDGET = 500
MAX_BUDGET = 8000

# 各部门可用工具（与 department._DEPT_TOOLS 一致，此处独立定义避免循环导入）
DEPT_TOOL_WHITELIST: dict[str, tuple[str, ...]] = {
    "accounting": ("tool_get_ledger_view", "tool_get_health_check", "tool_get_trend"),
    "risk": ("tool_get_risk_flags", "tool_get_budget", "tool_get_health_check"),
    "invest": ("tool_get_market_view", "tool_get_goals", "tool_get_kline", "tool_get_quote"),
    "bookkeeping": ("tool_get_ledger_view", "tool_get_trend", "tool_get_budget"),
}

DEPT_DUTIES: dict[str, str] = {
    "accounting": "编制收支/结余报表，核对数字口径",
    "risk": "扫描风控信号（集中度/应急金/负债/预算漂移）",
    "invest": "复盘持仓与市场表现，看目标进度",
    "bookkeeping": "核对流水与分类质量，看月度趋势",
}


def _system_prompt(lang: str = "zh") -> str:
    """派工提示词：把部门职责、工具白名单、输出格式一次性说清。"""
    dept_lines = "\n".join(
        f"- {d}（{DEPT_TITLES[d]}）：{DEPT_DUTIES[d]}；可用工具 {', '.join(DEPT_TOOL_WHITELIST[d])}"
        for d in DEPARTMENTS
    )
    if lang == "en":
        return (
            "You are a dispatcher for a personal finance agent team. "
            "Split the owner's request into work orders, one per department. "
            "Only include departments genuinely needed — do not dispatch all four by default.\n"
            f"Departments:\n{dept_lines}\n"
            'Output JSON only: {"orders":[{"dept":"accounting","task":"...",'
            '"tools_allowed":["tool_x"],"budget_tokens":4000}]}\n'
            "Rules: dept must be one of the four; task <= 100 chars; "
            "each department appears at most once; budget_tokens between 500 and 8000."
        )
    return (
        "你是个人财务 Agent 团队的派工员。把老板的一句话拆成工单，每个部门最多一张。"
        "只派真正需要的部门——不要默认派全部四个；简单问题派一个就够。\n"
        f"部门与职责：\n{dept_lines}\n"
        '只输出 JSON：{"orders":[{"dept":"accounting","task":"...",'
        '"tools_allowed":["tool_x"],"budget_tokens":4000}]}\n'
        "要求：dept 只能是四个之一；task 不超过 100 字；同一部门最多出现一次；"
        "budget_tokens 在 500-8000 之间。"
    )


def _sanitize(plan: DispatchPlan) -> list[WorkOrder]:
    """把模型派工计划清洗成可执行工单。

    - 工具名必须在部门白名单内（模型自己编的工具直接剔除）
    - budget_tokens 夹到 MIN_BUDGET..MAX_BUDGET
    - 空工具列表时回落到该部门全部合法工具（模型漏填不该让部门无工具可用）
    """
    orders: list[WorkOrder] = []
    for draft in plan.orders:
        allowed = DEPT_TOOL_WHITELIST[draft.dept]
        picked = [t for t in draft.tools_allowed if t in allowed]
        if not picked:
            picked = list(allowed)
        budget = max(MIN_BUDGET, min(MAX_BUDGET, int(draft.budget_tokens)))
        orders.append(
            WorkOrder(
                dept=draft.dept,
                task=draft.task,
                tools_allowed=picked,
                budget_tokens=budget,
            )
        )
    return orders


async def dispatch(
    question: str, lang: str = "zh", timeout: float = 15.0
) -> tuple[list[WorkOrder], str]:
    """LLM 派工。返回 (工单列表, 派工来源)。

    派工来源用于可观测性：
    - "llm"      模型成功产出并通过校验
    - "rules"    模型不可用/超时/输出非法，回落到规则派工

    永不抛错：派工失败必须让部门模式仍能运行（宁可派得不理想，也不能整个功能不可用）。
    """
    from . import department

    if not await llm.llm_available():
        return department.decompose(question), "rules"

    try:
        raw = await llm.json_complete(_system_prompt(lang), question, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — 模型层任何异常都必须降级，不能拖垮部门模式
        log.warning("dispatch.llm_error: %s — 回落到规则派工", str(exc)[:200])
        return department.decompose(question), "rules"
    if not isinstance(raw, dict):
        log.info("dispatch.llm_unavailable: 回落到规则派工")
        return department.decompose(question), "rules"

    try:
        plan = DispatchPlan.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 — 模型输出不合法是常态，不是异常
        log.warning("dispatch.invalid_plan: %s — 回落到规则派工", str(exc)[:200])
        return department.decompose(question), "rules"

    orders = _sanitize(plan)
    if not orders:  # pragma: no cover — DispatchPlan 已保证至少一条
        return department.decompose(question), "rules"
    log.info(
        "dispatch.llm_ok: depts=%s", ",".join(o.dept for o in orders)
    )
    return orders, "llm"


def parse_plan_json(text: str) -> DispatchPlan | None:
    """从模型返回的文本里解析派工计划（供测试与离线校验）。

    模型有时会把 JSON 包在 ```json 代码块里，这里一并容忍。
    """
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 去掉首尾围栏
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 退一步：从全文里截取第一个 {...}
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    try:
        return DispatchPlan.model_validate(data)
    except Exception:  # noqa: BLE001
        return None
