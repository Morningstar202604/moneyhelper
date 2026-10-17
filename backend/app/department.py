"""M3 财务部门模式（第一刀）：工单分解 → 四部门并行 → 秘书汇总呈批。

与 agent_graph 的分工：
  - agent_graph = 单轮问答编排（supervisor 线性流水线）；
  - 本模块 = 「老板一句话，部门自己干」：把问题拆成工单，Send 式并行派发，
    各部门用确定性工具取数（数字仍不出确定性内核），秘书交叉汇总成呈批件。

第一刀范围（骨架 + 确定性内核直连，不依赖 LLM）：
  - 工单分解：关键词规则（后续接 LLM 结构化输出）；
  - 部门执行：直接调用 tools.py 确定性工具（无模型也可用）；
  - 秘书汇总：合并 + 同口径数字交叉对账（发现冲突标红）。
后续迭代：LLM 派工 / 各部门 agent 工具循环 / HITL 呈批 / 实况看板事件流。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from . import analysis, tools
from .logging_utils import get_logger


def department_mod():
    return __import__(__name__, fromlist=[""])

log = get_logger(__name__)

Emit = Callable[[dict[str, Any]], Awaitable[None]]

DEPTS = ("accounting", "risk", "invest", "bookkeeping")
DEPT_TITLES = {
    "accounting": "会计部",
    "risk": "风控部",
    "invest": "投资部",
    "bookkeeping": "记账部",
}


@dataclass
class WorkOrder:
    dept: str
    task: str
    tools_allowed: list[str] = field(default_factory=list)
    status: str = "pending"  # pending/running/done/failed
    output: str = ""
    error: str = ""


def _dispatch_rules() -> list[tuple[str, tuple[str, ...], str]]:
    """关键词 → (部门, 任务描述)。顺序即优先级；命中即派发。"""
    return [
        ("invest", ("持仓", "股票", "基金", "盈亏", "市值", "行情", "etf"),
         "复盘当前持仓与市场表现"),
        ("risk", ("风险", "风险提示", "健康", "应急", "负债", "DTI", "集中度", "超支", "预算"),
         "扫描风控信号（集中度/应急金/负债/预算漂移）"),
        ("bookkeeping", ("记", "入账", "花了", "消费", "支出明细", "分类"),
         "核对近期记账与分类质量"),
        ("accounting", ("汇总", "总结", "盘", "体检", "报告", "现金流", "结余", "收支", "财务"),
         "编制本期收支与结余报表"),
    ]


def decompose(question: str) -> list[WorkOrder]:
    """把老板的一句话拆成工单（规则版；LLM 结构化派工为后续迭代）。"""
    q = question.lower()
    orders: list[WorkOrder] = []
    seen: set[str] = set()
    for dept, kws, task in _dispatch_rules():
        if dept in seen:
            continue
        if any(kw.lower() in q for kw in kws):
            orders.append(WorkOrder(dept=dept, task=task, tools_allowed=_dept_tools(dept)))
            seen.add(dept)
    if not orders:
        # 兜底：财务类问题默认会计部+风控部各出一份
        orders = [
            WorkOrder(dept="accounting", task="编制本期收支与结余报表", tools_allowed=_dept_tools("accounting")),
            WorkOrder(dept="risk", task="扫描风控信号", tools_allowed=_dept_tools("risk")),
        ]
    return orders


def _dept_tools(dept: str) -> list[str]:
    return {
        "accounting": ["tool_get_ledger_view", "tool_get_health_check"],
        "risk": ["tool_get_risk_flags", "tool_get_budget"],
        "invest": ["tool_get_market_view", "tool_get_goals"],
        "bookkeeping": ["tool_get_ledger_view", "tool_get_trend"],
    }[dept]


_DEPT_RUNNERS: dict[str, str] = {
    "accounting": "_run_accounting",
    "risk": "_run_risk",
    "invest": "_run_invest",
    "bookkeeping": "_run_bookkeeping",
}


async def _run_accounting() -> str:
    ledger = await tools.tool_get_ledger_view({})
    health = await tools.tool_get_health_check({})
    return f"【账本视角】\n{ledger}\n\n【健康体检】\n{health}"


async def _run_risk() -> str:
    flags = await tools.tool_get_risk_flags({})
    budget = await tools.tool_get_budget({})
    return f"【风控信号】\n{flags}\n\n【预算执行】\n{budget}"


async def _run_invest() -> str:
    market = await tools.tool_get_market_view({})
    goals = await tools.tool_get_goals({})
    return f"【市场视角】\n{market}\n\n【目标进度】\n{goals}"


async def _run_bookkeeping() -> str:
    ledger = await tools.tool_get_ledger_view({})
    trend = await tools.tool_get_trend({})
    return f"【账本视角】\n{ledger}\n\n【月度趋势】\n{trend}"


async def _execute_order(order: WorkOrder, emit: Emit | None) -> WorkOrder:
    order.status = "running"
    if emit:
        await emit({"type": "dept", "dept": order.dept, "status": "running", "task": order.task})
    try:
        # 按名字解析：便于测试替换与未来热插拔部门实现
        order.output = await getattr(department_mod(), _DEPT_RUNNERS[order.dept])()
        order.status = "done"
    except Exception as e:  # noqa: BLE001 — 部门失败不拖垮整体呈批
        log.warning("dept_failed dept=%s error=%s", order.dept, str(e))
        order.status = "failed"
        order.error = str(e)[:200]
    if emit:
        await emit({"type": "dept", "dept": order.dept, "status": order.status})
    return order


async def _secretary(orders: list[WorkOrder], question: str) -> dict[str, Any]:
    """秘书汇总：合并部门产出 + 同口径交叉对账（数字冲突标红）。"""
    sections = []
    conflicts: list[str] = []
    for o in orders:
        title = DEPT_TITLES.get(o.dept, o.dept)
        if o.status == "done":
            sections.append(f"## {title}\n{o.output}")
        else:
            sections.append(f"## {title}（未完成：{o.error or o.status}）")

    # 交叉对账：会计与投资都报总市值时口径必须一致（当前为占位规则，
    # 后续各部门输出结构化 metrics 后做精确对账）
    market_views = [o.output for o in orders if o.status == "done" and "总市值" in o.output]
    if len(market_views) > 1 and len({m for m in market_views}) > 1:
        conflicts.append("总市值口径不一致，请复核")

    return {
        "question": question,
        "orders": [
            {"dept": o.dept, "task": o.task, "status": o.status, "error": o.error}
            for o in orders
        ],
        "report": "\n\n---\n\n".join(sections),
        "conflicts": conflicts,
        "disclaimer": analysis.DISCLAIMER,
    }


async def run_department_mode(
    question: str, emit: Emit | None = None, lang: str = "zh"
) -> dict[str, Any]:
    """部门模式入口：拆单 → 并行执行 → 秘书汇总呈批。"""
    orders = decompose(question)
    if emit:
        await emit({
            "type": "dept_start",
            "question": question,
            "orders": [{"dept": o.dept, "task": o.task} for o in orders],
        })
    # 并行派发（Send 式）；return_exceptions 确保等全部部门结束，不留后台任务拖垮事件循环
    results = await asyncio.gather(
        *(_execute_order(o, emit) for o in orders), return_exceptions=True
    )
    done: list[WorkOrder] = []
    for o, r in zip(orders, results, strict=False):
        if isinstance(r, Exception):
            o.status, o.error = "failed", str(r)[:200]
        done.append(o)
    report = await _secretary(list(done), question)
    if emit:
        await emit({"type": "dept_final", "conflicts": report["conflicts"]})
    return report
