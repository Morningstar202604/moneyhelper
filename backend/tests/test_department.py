"""M3 部门模式回归：拆单规则 / 并行执行 / 秘书汇总呈批。"""
from __future__ import annotations

from app import department
from app.department import WorkOrder, decompose, run_department_mode


def test_decompose_rules():
    orders = decompose("把我的持仓和风险盘一下")
    depts = [o.dept for o in orders]
    assert "invest" in depts and "risk" in depts
    for o in orders:
        assert o.tools_allowed, "每个工单必须带工具白名单"
        assert o.status == "pending"


def test_decompose_fallback():
    orders = decompose("在吗")  # 无关键词命中 → 兜底会计+风控
    assert [o.dept for o in orders] == ["accounting", "risk"]


async def test_parallel_and_secretary(temp_db):
    """并行执行 + 呈批件结构；部门失败不拖垮整体。"""
    seen: list[str] = []
    events: list[dict] = []

    async def emit(e: dict) -> None:
        events.append(e)

    real_risk = department._run_risk

    async def boom() -> str:
        seen.append("risk")
        raise RuntimeError("风控部网络故障")

    department._run_risk = boom  # type: ignore[method-assign]
    try:
        report = await run_department_mode("帮我盘一下持仓和风险", emit)
    finally:
        department._run_risk = real_risk  # type: ignore[method-assign]

    assert report["question"] == "帮我盘一下持仓和风险"
    by_dept = {o["dept"]: o for o in report["orders"]}
    assert by_dept["risk"]["status"] == "failed"
    assert "网络故障" in by_dept["risk"]["error"]
    assert by_dept["invest"]["status"] == "done"
    assert "【市场视角】" in report["report"]
    assert "未完成" in report["report"]  # 失败部门如实呈报，不冒充
    assert report["disclaimer"]
    # 事件流：start/running/…
    assert events[0]["type"] == "dept_start"


async def test_secretary_conflict_detection(temp_db):
    """同口径数字冲突 → 标红（占位规则：多个不同“总市值”输出）。"""
    o1 = WorkOrder(dept="invest", task="t", status="done", output="总市值 100 元")
    o2 = WorkOrder(dept="accounting", task="t", status="done", output="总市值 200 元")
    report = await department._secretary([o1, o2], "q")
    assert report["conflicts"], "口径冲突必须被秘书标出"
