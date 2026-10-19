"""M3.3 部门 agent 测试。

部门 agent 的价值是"部门自己决定看什么"，但风险也在这里：模型可能调用
不该调的工具、编造数字、或跑飞。测试重点是约束真的生效：
1. 工具白名单按部门隔离（风险部调不到行情工具）
2. metrics 从回答末尾正确提取（秘书对账的前提）
3. 模型不可用/失败时退回确定性执行（离线可用是底线）
4. token 预算超支不判失败，但如实标注
"""

from __future__ import annotations

import pytest
from app import dept_agent
from app.dept_models import WorkOrder

# ---------------------------------------------------------------------------
# 工具白名单隔离
# ---------------------------------------------------------------------------


def test_dept_tools_are_isolated() -> None:
    """每个部门的工具集必须互不相同且非空（工具面按部门收窄）。"""
    for dept, names in dept_agent.DEPT_TOOLS.items():
        assert names, f"{dept} 没有可用工具"
    risk_tools = set(dept_agent.DEPT_TOOLS["risk"])
    invest_tools = set(dept_agent.DEPT_TOOLS["invest"])
    assert not (risk_tools & invest_tools - {"tool_get_health_check"})


def test_allowed_schemas_filtered_by_dept() -> None:
    """schema 列表只能是该部门白名单内的工具。"""
    schemas = dept_agent._allowed_schemas("risk")
    names = {t["function"]["name"] for t in schemas}
    assert names <= {"get_risk_flags", "get_budget", "get_health_check"}
    assert "get_quote" not in names, "风控部不该看到行情工具"


def test_allowed_impls_match_schemas() -> None:
    """实现表与 schema 表必须一一对应，否则模型调了工具却没实现。"""
    for dept in dept_agent.DEPT_TOOLS:
        schemas = {t["function"]["name"] for t in dept_agent._allowed_schemas(dept)}
        impls = set(dept_agent._allowed_impls(dept))
        assert schemas == impls, f"{dept}: schema {schemas} vs impl {impls}"


def test_every_dept_has_instructions() -> None:
    """每个部门都要有角色说明，否则 agent 不知道自己要产出什么。"""
    for dept in dept_agent.DEPT_TOOLS:
        inst = dept_agent.DEPT_INSTRUCTIONS.get(dept)
        assert inst and len(inst) > 30
        assert "metrics" in inst, f"{dept} 的说明没要求输出 metrics（对账会失效）"


# ---------------------------------------------------------------------------
# metrics 提取
# ---------------------------------------------------------------------------


def test_extract_metrics_from_last_line() -> None:
    text = '本月支出 21265 元。\n{"metrics":{"expense":21265.0}}'
    body, metrics = dept_agent._extract_metrics(text)
    assert metrics == {"expense": 21265.0}
    assert "metrics" not in body
    assert "本月支出" in body


def test_extract_metrics_ignores_malformed() -> None:
    text = '结论：正常\n{"metrics": {broken'
    body, metrics = dept_agent._extract_metrics(text)
    assert metrics == {}
    assert body == text


def test_extract_metrics_non_numeric_values_dropped() -> None:
    """非数字值丢弃（不能让 "N/A" 污染对账）。"""
    text = 'x\n{"metrics":{"expense":"N/A","income":100}}'
    _, metrics = dept_agent._extract_metrics(text)
    assert metrics == {"income": 100.0}


def test_extract_metrics_without_json() -> None:
    body, metrics = dept_agent._extract_metrics("纯文本回答，没有结构化指标")
    assert metrics == {}
    assert body


def test_extract_metrics_empty_input() -> None:
    assert dept_agent._extract_metrics("") == ("", {})


def test_extract_metrics_scans_only_last_few_lines() -> None:
    """只在末尾几行找，避免把正文里的示例 JSON 误当指标。"""
    text = '示例：{"metrics":{"expense":1}}\n' + "正文\n" * 20 + "结尾没有指标"
    _, metrics = dept_agent._extract_metrics(text)
    assert metrics == {}


# ---------------------------------------------------------------------------
# 执行路径与降级
# ---------------------------------------------------------------------------


@pytest.fixture
def no_llm(monkeypatch):
    async def _unavailable() -> bool:
        return False

    monkeypatch.setattr(dept_agent.llm, "llm_available", _unavailable)


async def test_falls_back_when_no_llm(temp_db, no_llm):
    """无模型时走确定性执行，工单仍完成且有 metrics。"""
    order = WorkOrder(dept="accounting", task="出报表")
    out = await dept_agent.run_dept_agent(order)
    assert out.status == "done"
    assert out.output
    assert "expense" in out.metrics, "对账需要的指标必须有"


async def test_fallback_produces_reconcilable_metrics(temp_db, no_llm):
    """会计与记账的 expense 同口径：降级路径下也一致（对账不会假冲突）。"""
    from app import department

    a = await dept_agent.run_dept_agent(WorkOrder(dept="accounting", task="x"))
    b = await dept_agent.run_dept_agent(WorkOrder(dept="bookkeeping", task="x"))
    assert a.metrics["expense"] == b.metrics["expense"]
    assert department.reconcile([a, b]) == []


async def test_agent_failure_falls_back(temp_db, monkeypatch):
    """agent 循环抛异常 → 退回确定性执行，工单不失败。"""
    from app import agent

    async def _unavailable() -> bool:
        return True

    async def _boom(*a, **kw):
        raise RuntimeError("agent exploded")

    monkeypatch.setattr(dept_agent.llm, "llm_available", _unavailable)
    monkeypatch.setattr(agent, "run_agent", _boom)

    out = await dept_agent.run_dept_agent(WorkOrder(dept="risk", task="扫风险"))
    assert out.status == "done"
    assert out.output


async def test_agent_path_used_when_llm_available(temp_db, monkeypatch):
    """模型可用且成功 → 用 agent 产出（不是确定性模板）。"""
    from app import agent

    async def _available() -> bool:
        return True

    async def _fake_run(question, emit, **kw):
        assert kw["system"] == dept_agent.DEPT_INSTRUCTIONS["risk"]
        assert {t["function"]["name"] for t in kw["tools_list"]} == {
            "get_risk_flags",
            "get_budget",
            "get_health_check",
        }
        return {
            "answer": '模型发现 3 项风险。\n{"metrics":{"risk_flags":3}}',
            "tools_used": ["get_risk_flags"],
        }

    monkeypatch.setattr(dept_agent.llm, "llm_available", _available)
    monkeypatch.setattr(agent, "run_agent", _fake_run)

    out = await dept_agent.run_dept_agent(WorkOrder(dept="risk", task="扫风险"))
    assert out.status == "done"
    assert "模型发现" in out.output
    assert out.metrics == {"risk_flags": 3.0}
    assert out.tokens_used > 0


async def test_agent_empty_answer_falls_back(temp_db, monkeypatch):
    """模型返回空回答 → 视为失败并降级（不能给秘书一个空部门）。"""
    from app import agent

    async def _available() -> bool:
        return True

    async def _empty(question, emit, **kw):
        return {"answer": ""}

    monkeypatch.setattr(dept_agent.llm, "llm_available", _available)
    monkeypatch.setattr(agent, "run_agent", _empty)

    out = await dept_agent.run_dept_agent(WorkOrder(dept="invest", task="看持仓"))
    assert out.status == "done"
    assert out.output, "降级后必须有产出"


# ---------------------------------------------------------------------------
# token 预算
# ---------------------------------------------------------------------------


async def test_over_budget_annotated_but_not_failed(temp_db, monkeypatch):
    """超预算不判失败（产出仍有价值），但要在 error 字段如实标注。"""
    from app import agent

    async def _available() -> bool:
        return True

    async def _long(question, emit, **kw):
        return {"answer": "很长的回答" * 5000 + '\n{"metrics":{"expense":1}}'}

    monkeypatch.setattr(dept_agent.llm, "llm_available", _available)
    monkeypatch.setattr(agent, "run_agent", _long)

    order = WorkOrder(dept="accounting", task="x", budget_tokens=500)
    out = await dept_agent.run_dept_agent(order)
    assert out.status == "done", "超支不是失败"
    assert out.tokens_used > out.budget_tokens
    assert "超支" in out.error


async def test_within_budget_no_annotation(temp_db, monkeypatch):
    from app import agent

    async def _available() -> bool:
        return True

    async def _short(question, emit, **kw):
        return {"answer": '短回答\n{"metrics":{"expense":1}}'}

    monkeypatch.setattr(dept_agent.llm, "llm_available", _available)
    monkeypatch.setattr(agent, "run_agent", _short)

    out = await dept_agent.run_dept_agent(
        WorkOrder(dept="accounting", task="x", budget_tokens=8000)
    )
    assert out.error == ""


# ---------------------------------------------------------------------------
# 与部门模式集成
# ---------------------------------------------------------------------------


async def test_department_mode_agent_path(temp_db, monkeypatch):
    """部门模式默认走 agent 路径（模型可用时）。"""
    from app import agent, department

    async def _available() -> bool:
        return True

    async def _fake(question, emit, **kw):
        return {"answer": '产出\n{"metrics":{"expense":21265}}'}

    monkeypatch.setattr(dept_agent.llm, "llm_available", _available)
    monkeypatch.setattr(agent, "run_agent", _fake)

    report = await department.run_department_mode(
        "盘一下", use_llm_dispatch=False, use_agent=True
    )
    assert all(o["status"] == "done" for o in report["orders"])
    assert all(o["tokens_used"] > 0 for o in report["orders"])


async def test_department_mode_can_force_deterministic(temp_db):
    """显式关闭 agent（离线调试）：确定性路径仍产出完整呈批件。"""
    from app import department

    report = await department.run_department_mode(
        "盘一下", use_llm_dispatch=False, use_agent=False
    )
    assert report["verdict"]
    assert any("视角" in o["metrics"] or o["metrics"] for o in report["orders"])
