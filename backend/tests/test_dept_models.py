"""M3.1 工单 schema + 交叉对账测试。

重点不是"字段能不能赋值"，而是三个约束真的生效：
1. 非法部门/状态会被拒绝（否则 LLM 派工出错时静默少一个部门）
2. LLM 只能提交派工字段，不能伪造运行时状态（id/status/output/metrics）
3. 交叉对账按结构化 metrics 比对，不靠正则抠文本
"""

from __future__ import annotations

import pytest
from app import department
from app.dept_models import (
    DEPARTMENTS,
    DispatchPlan,
    WorkOrder,
    WorkOrderDraft,
    order_to_dict,
    to_orders,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# 工单模型约束
# ---------------------------------------------------------------------------


def test_valid_order_defaults() -> None:
    o = WorkOrder(dept="risk", task="扫风险")
    assert o.status == "pending"
    assert o.budget_tokens == 4000
    assert o.id and len(o.id) == 12
    assert o.metrics == {}


@pytest.mark.parametrize("dept", ["sales", "IT", "", "Accounting"])
def test_invalid_dept_rejected(dept: str) -> None:
    """部门名必须是四个之一，大小写也不放宽（避免 LLM 输出 'Accounting' 时静默失败）。"""
    with pytest.raises(ValidationError):
        WorkOrder(dept=dept, task="x")  # type: ignore[arg-type]


@pytest.mark.parametrize("status", ["unknown", "DONE", "cancelled"])
def test_invalid_status_rejected(status: str) -> None:
    with pytest.raises(ValidationError):
        WorkOrder(dept="risk", task="x", status=status)  # type: ignore[arg-type]


@pytest.mark.parametrize("task", ["", "   ", "\n\t"])
def test_blank_task_rejected(task: str) -> None:
    """空白任务意味着这次派工没有实质内容，应该在构造时就失败。"""
    with pytest.raises(ValidationError):
        WorkOrder(dept="risk", task=task)


def test_task_is_trimmed() -> None:
    assert WorkOrder(dept="risk", task="  扫风险  ").task == "扫风险"


def test_budget_bounds() -> None:
    """预算必须有下界（防止 0 预算让部门无法执行）与上界（防止吃掉整轮预算）。"""
    with pytest.raises(ValidationError):
        WorkOrder(dept="risk", task="x", budget_tokens=50)
    with pytest.raises(ValidationError):
        WorkOrder(dept="risk", task="x", budget_tokens=1_000_000)
    assert WorkOrder(dept="risk", task="x", budget_tokens=100).budget_tokens == 100


def test_extra_fields_rejected() -> None:
    """模型不该能塞入未定义字段（extra=forbid）。"""
    with pytest.raises(ValidationError):
        WorkOrder(dept="risk", task="x", sneaky="value")  # type: ignore[call-arg]


def test_over_budget() -> None:
    o = WorkOrder(dept="risk", task="x", budget_tokens=100)
    assert not o.over_budget()
    o.tokens_used = 101
    assert o.over_budget()


# ---------------------------------------------------------------------------
# LLM 派工模型（M3.2 的输出形态）
# ---------------------------------------------------------------------------


def test_draft_cannot_set_runtime_fields() -> None:
    """派工草案不能伪造运行时状态（id/status/output/metrics）。

    这些是执行阶段产生的，若模型能直接设，审计与看板就不可信了。
    """
    for field in ("id", "status", "output", "metrics", "tokens_used"):
        with pytest.raises(ValidationError):
            WorkOrderDraft.model_validate(
                {"dept": "risk", "task": "x", field: "tampered"}
            )


def test_plan_rejects_duplicate_depts() -> None:
    """同一部门在一轮派工里出现两次 → 拒绝。

    重复会把同一件事派两遍，执行时重复取数，对账还会出现"自己跟自己冲突"。
    """
    with pytest.raises(ValidationError):
        DispatchPlan(
            orders=[
                {"dept": "risk", "task": "a"},
                {"dept": "risk", "task": "b"},
            ]
        )


def test_plan_requires_at_least_one_order() -> None:
    with pytest.raises(ValidationError):
        DispatchPlan(orders=[])


def test_plan_to_orders() -> None:
    plan = DispatchPlan(
        orders=[
            {"dept": "accounting", "task": "编报表", "tools_allowed": ["t1"]},
            {"dept": "risk", "task": "扫风险"},
        ]
    )
    orders = to_orders(plan)
    assert [o.dept for o in orders] == ["accounting", "risk"]
    assert orders[0].tools_allowed == ["t1"]
    assert all(o.status == "pending" for o in orders)


def test_order_to_dict_excludes_output() -> None:
    """SSE/API 返回的工单不含 output（完整文本走 report，避免事件体过大）。"""
    o = WorkOrder(dept="risk", task="x", output="很长的文本" * 100)
    d = order_to_dict(o)
    assert "output" not in d
    assert set(d) == {
        "id",
        "dept",
        "task",
        "status",
        "metrics",
        "tokens_used",
        "budget_tokens",
        "error",
    }


# ---------------------------------------------------------------------------
# 派工（规则版）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    ["盘一下上季度", "这个月财务状况怎么样", "整体体检一下", "看看家底"],
)
def test_full_review_dispatches_all_depts(question: str) -> None:
    """全面盘点类问题必须派全部四部门。

    只派一个部门时，部门模式退化成普通问答，失去多视角交叉的意义。
    """
    orders = department.decompose(question)
    assert {o.dept for o in orders} == set(DEPARTMENTS)


@pytest.mark.parametrize(
    ("question", "expect"),
    [
        ("我的风险大吗", "risk"),
        ("看看持仓", "invest"),
        ("我的支出明细", "bookkeeping"),
    ],
)
def test_specific_question_dispatches_relevant_dept(question: str, expect: str) -> None:
    """具体问题只派相关部门，不滥用全量盘点（省 token）。"""
    orders = department.decompose(question)
    assert [o.dept for o in orders] == [expect]


def test_unmatched_question_falls_back_to_two_depts() -> None:
    """完全没命中的问题兜底派会计 + 风控：至少要知道"账本现状"和"风险信号"。"""
    orders = department.decompose("你好呀")
    assert {o.dept for o in orders} == {"accounting", "risk"}


# ---------------------------------------------------------------------------
# 交叉对账
# ---------------------------------------------------------------------------


def _order(dept: str, metrics: dict[str, float], status: str = "done") -> WorkOrder:
    return WorkOrder(dept=dept, task="t", metrics=metrics, status=status)  # type: ignore[arg-type]


def test_reconcile_detects_mismatch() -> None:
    """同口径指标两部门报的数值不同 → 冲突，并指明是哪两个部门。"""
    orders = [
        _order("accounting", {"expense": 21265.0}),
        _order("bookkeeping", {"expense": 21000.0}),
    ]
    conflicts = department.reconcile(orders)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["metric"] == "expense"
    assert set(c["depts"]) == {"accounting", "bookkeeping"}
    # 详情里数字带千分位（21,265.00），断言去掉逗号再比
    flat = c["detail"].replace(",", "")
    assert "21265" in flat and "21000" in flat


def test_reconcile_passes_when_equal() -> None:
    orders = [
        _order("accounting", {"expense": 21265.0}),
        _order("bookkeeping", {"expense": 21265.0}),
    ]
    assert department.reconcile(orders) == []


def test_reconcile_ignores_non_shared_metrics() -> None:
    """只由一个部门产出的指标不参与对账（比对没有意义）。"""
    orders = [
        _order("invest", {"total_market_value": 282540.0}),
        _order("risk", {"risk_flags": 4.0}),
    ]
    assert department.reconcile(orders) == []


def test_reconcile_ignores_failed_depts() -> None:
    """失败的部门没有可信数字，不能拿它参与对账。"""
    orders = [
        _order("accounting", {"expense": 21265.0}),
        _order("bookkeeping", {"expense": 1.0}, status="failed"),
    ]
    assert department.reconcile(orders) == []


def test_reconcile_rounds_to_cents() -> None:
    """浮点误差（21265.0 vs 21265.000001）不算冲突。"""
    orders = [
        _order("accounting", {"expense": 21265.0}),
        _order("bookkeeping", {"expense": 21265.0000001}),
    ]
    assert department.reconcile(orders) == []
