"""M3.2 LLM 派工测试。

派工是部门模式的入口，模型输出的不可信程度最高。测试重点在三条防线：
1. schema 校验真的会拒绝非法输出（而不是"差不多就行"）
2. 模型写的工具名不可信——必须按部门白名单过滤
3. 模型任何形式的失败都必须回落到规则派工（功能不能因模型抖动而不可用）
"""

from __future__ import annotations

import pytest
from app import dept_dispatch
from app.dept_models import DispatchPlan


class _FakeLLM:
    """可编程的假 LLM：控制 llm_available 与 json_complete 的返回。"""

    def __init__(self, available: bool = True, response=None, raises: bool = False):
        self.available = available
        self.response = response
        self.raises = raises
        self.calls: list[tuple[str, str]] = []

    async def llm_available(self) -> bool:
        return self.available

    async def json_complete(self, system: str, user: str, timeout: float = 20.0):
        self.calls.append((system, user))
        if self.raises:
            raise RuntimeError("llm exploded")
        return self.response


@pytest.fixture
def patch_llm(monkeypatch):
    def _patch(fake: _FakeLLM):
        monkeypatch.setattr(dept_dispatch, "llm", fake)
        return fake

    return _patch


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


async def test_llm_dispatch_success(patch_llm):
    fake = patch_llm(
        _FakeLLM(
            response={
                "orders": [
                    {"dept": "accounting", "task": "出上季度收支表", "budget_tokens": 3000},
                    {"dept": "invest", "task": "看持仓是否要调整", "budget_tokens": 2000},
                ]
            }
        )
    )
    orders, src = await dept_dispatch.dispatch("这季度是不是该调整一下了")
    assert src == "llm"
    assert [o.dept for o in orders] == ["accounting", "invest"]
    assert fake.calls, "必须真的调用模型"


async def test_llm_sees_dept_duties_and_tool_whitelist(patch_llm):
    """提示词必须包含部门职责与工具白名单，否则模型只能瞎猜。"""
    fake = patch_llm(_FakeLLM(response={"orders": [{"dept": "risk", "task": "x"}]}))
    await dept_dispatch.dispatch("我的风险大吗")
    system, user = fake.calls[0]
    assert "风控部" in system
    assert "tool_get_risk_flags" in system
    assert user == "我的风险大吗"


async def test_english_prompt(patch_llm):
    fake = patch_llm(_FakeLLM(response={"orders": [{"dept": "risk", "task": "x"}]}))
    await dept_dispatch.dispatch("how risky am I", lang="en")
    system, _ = fake.calls[0]
    assert "dispatcher" in system and "Departments" in system


# ---------------------------------------------------------------------------
# 工具白名单过滤（模型不可信）
# ---------------------------------------------------------------------------


async def test_invented_tools_filtered(patch_llm):
    """模型编造的工具名必须被剔除（只保留该部门白名单内的）。"""
    patch_llm(
        _FakeLLM(
            response={
                "orders": [
                    {
                        "dept": "risk",
                        "task": "扫描风险",
                        "tools_allowed": ["tool_get_risk_flags", "rm_rf_everything"],
                    }
                ]
            }
        )
    )
    orders, _ = await dept_dispatch.dispatch("风险")
    assert orders[0].tools_allowed == ["tool_get_risk_flags"]


async def test_cross_dept_tools_filtered(patch_llm):
    """风险部不能借用投资部的工具（工具面按部门隔离）。"""
    patch_llm(
        _FakeLLM(
            response={
                "orders": [
                    {
                        "dept": "risk",
                        "task": "x",
                        "tools_allowed": ["tool_get_quote"],
                    }
                ]
            }
        )
    )
    orders, _ = await dept_dispatch.dispatch("风险")
    # 白名单里没有合法项 → 回落到该部门全部合法工具
    assert "tool_get_quote" not in orders[0].tools_allowed
    assert set(orders[0].tools_allowed) == set(
        dept_dispatch.DEPT_TOOL_WHITELIST["risk"]
    )


async def test_empty_tools_falls_back_to_all_allowed(patch_llm):
    """模型漏填工具时用该部门全部合法工具，而不是让部门无工具可用。"""
    patch_llm(_FakeLLM(response={"orders": [{"dept": "invest", "task": "x"}]}))
    orders, _ = await dept_dispatch.dispatch("持仓")
    assert set(orders[0].tools_allowed) == set(
        dept_dispatch.DEPT_TOOL_WHITELIST["invest"]
    )


# ---------------------------------------------------------------------------
# 预算夹逼
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expect"),
    [
        (100, dept_dispatch.MIN_BUDGET),
        (99999, dept_dispatch.MAX_BUDGET),
        (4000, 4000),
    ],
)
async def test_budget_clamped(patch_llm, given: int, expect: int):
    """预算夹到合理区间：太少部门跑不完，太多挤占其他部门。"""
    patch_llm(
        _FakeLLM(
            response={
                "orders": [
                    {"dept": "accounting", "task": "x", "budget_tokens": given}
                ]
            }
        )
    )
    orders, _ = await dept_dispatch.dispatch("账")
    assert orders[0].budget_tokens == expect


# ---------------------------------------------------------------------------
# 降级（三道防线的第三道）
# ---------------------------------------------------------------------------


async def test_fallback_when_llm_unavailable(patch_llm):
    fake = patch_llm(_FakeLLM(available=False))
    orders, src = await dept_dispatch.dispatch("盘一下")
    assert src == "rules"
    assert orders, "规则派工必须有结果"
    assert not fake.calls, "模型不可用时不该调用"


async def test_fallback_when_llm_returns_none(patch_llm):
    patch_llm(_FakeLLM(response=None))
    orders, src = await dept_dispatch.dispatch("盘一下")
    assert src == "rules" and orders


async def test_fallback_when_llm_raises(patch_llm):
    """模型抛异常不能让部门模式崩掉。"""
    patch_llm(_FakeLLM(raises=True))
    orders, src = await dept_dispatch.dispatch("盘一下")
    assert src == "rules" and orders


@pytest.mark.parametrize(
    "bad_response",
    [
        {"orders": []},  # 空派工
        {"orders": [{"dept": "sales", "task": "x"}]},  # 非法部门
        {"orders": [{"dept": "risk", "task": "x"}, {"dept": "risk", "task": "y"}]},  # 重复
        {"orders": [{"dept": "risk", "task": ""}]},  # 空任务
        {"orders": [{"dept": "risk", "task": "x", "unknown": 1}]},  # 多余字段
        {"wrong_key": []},  # 结构不对
    ],
)
async def test_fallback_on_invalid_plan(patch_llm, bad_response):
    """任何 schema 不合法的输出都必须回落到规则派工。"""
    patch_llm(_FakeLLM(response=bad_response))
    orders, src = await dept_dispatch.dispatch("盘一下")
    assert src == "rules"
    assert orders


# ---------------------------------------------------------------------------
# 解析容错（模型常见的前后废话）
# ---------------------------------------------------------------------------


def test_parse_plan_strips_code_fence():
    text = '```json\n{"orders":[{"dept":"risk","task":"扫风险"}]}\n```'
    plan = dept_dispatch.parse_plan_json(text)
    assert isinstance(plan, DispatchPlan)
    assert plan.orders[0].dept == "risk"


def test_parse_plan_extracts_from_prose():
    text = '好的，我建议这样派工：{"orders":[{"dept":"invest","task":"看持仓"}]} 以上。'
    plan = dept_dispatch.parse_plan_json(text)
    assert plan is not None and plan.orders[0].dept == "invest"


def test_parse_plan_rejects_garbage():
    assert dept_dispatch.parse_plan_json("我无法完成这个任务") is None
    assert dept_dispatch.parse_plan_json("") is None


# ---------------------------------------------------------------------------
# 与部门模式集成
# ---------------------------------------------------------------------------


async def test_run_department_mode_reports_dispatch_source(temp_db, monkeypatch):
    """呈批件要标明派工来源，便于排查"为什么少了个部门"。"""
    from app import department

    async def _fake_dispatch(question, lang="zh", timeout=15.0):
        from app.dept_models import WorkOrder

        return [WorkOrder(dept="risk", task="扫风险")], "llm"

    monkeypatch.setattr(dept_dispatch, "dispatch", _fake_dispatch)
    report = await department.run_department_mode("风险", use_llm_dispatch=True)
    assert report["dispatch"] == "llm"


async def test_run_department_mode_can_force_rules(temp_db):
    """显式关闭 LLM 派工（离线/调试场景）。"""
    from app import department

    report = await department.run_department_mode("盘一下", use_llm_dispatch=False)
    assert report["dispatch"] == "rules"
