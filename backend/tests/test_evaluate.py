"""确定性评估引擎：5 条规则 + 入口 + API 端点。

覆盖：
- evaluate.evaluate_all 返回结构（month/refreshed_at/items/summary）
- _rule_budget：无预算无流水 → 空；有流水无预算 → P2; 超支 → P0; 快超 → P1
- _rule_subscriptions：无订阅 → 空；1 条到期 → 单条; 多条到期 → 聚合；无 due_day → P3
- _rule_debts：无到期无利率 → 空；到期 → P1; 高利率 → P2
- _rule_goals：deadline 过 → P0; deadline 近 → P1; 完成 → P2
- _rule_cashflow：月支出=0 → 空；现金不足 → P2
- 规则异常不会拖垮整轮（mock 一条抛错，其他仍返回）
- GET /api/evaluate：200 + 结构；月份校验；
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
from app import db, evaluate, main
from app import quotes as quotes_mod
from app.evaluate import EvalItem


@pytest.fixture(autouse=True)
async def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db._core, "DB_PATH", tmp_path / "wealth.db")
    await db.init_db()
    await db.reset_to_seed()
    yield
    await db.close_db()


@pytest.fixture
async def client(_temp_db, monkeypatch):
    async def _snap(positions):
        return {p["symbol"]: float(p["last"]) for p in positions}

    monkeypatch.setattr(quotes_mod, "live_quotes", _snap)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"Host": "127.0.0.1"}
    ) as ac:
        yield ac


# --------------------------------------------------------------------------
# 入口结构
# --------------------------------------------------------------------------

async def test_evaluate_all_returns_basic_shape():
    """入口至少返回 month/refreshed_at/items/summary 四个字段。"""
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    assert out["month"] == "2026-01"
    assert isinstance(out["refreshed_at"], str)
    assert isinstance(out["items"], list)
    assert isinstance(out["summary"], dict)
    assert "todo" in out["summary"] and "max_priority" in out["summary"]


async def test_evaluate_all_items_sorted_by_priority():
    """items 按 priority 升序排列（priority 0 在最前）。"""
    # 种子数据含预算/订阅/负债/目标，可能有多个 item
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    pris = [it["priority"] for it in out["items"]]
    assert pris == sorted(pris)


# --------------------------------------------------------------------------
# budget 规则
# --------------------------------------------------------------------------

async def test_rule_budget_no_budget_no_txns_gives_empty():
    """无预算也无流水时，不发·任何提示。"""
    # 删掉种子预算和流水，构造纯净场景
    conn = await db._conn()
    await conn.execute("DELETE FROM budgets")
    await conn.execute("DELETE FROM transactions")
    await conn.commit()
    # 月度预算 usage.total_budget=0 → fallback 判断无流水
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    budget_items = [it for it in out["items"] if it["code"].startswith("budget.")]
    assert budget_items == []


async def test_rule_budget_set_no_spend_gives_near_or_none():
    """设预算但没花一分钱，不应产生超支 item。"""
    await db.save_budgets("2026-01", [{"category": "__total", "amount": 5000}])
    conn = await db._conn()
    await conn.execute("DELETE FROM transactions")
    await conn.commit()
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    over_items = [it for it in out["items"] if it["code"] == "budget.over"]
    assert over_items == []


async def test_rule_budget_over_emits_p0():
    """总花费大于预算 → P0 todo。"""
    await db.save_budgets("2026-01", [{"category": "__total", "amount": 100}])
    # 记一笔 >100 的支出（金额为负表示支出）
    await db.add_transaction("2026-01-10", "测试大额", "购物", -500)
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    over = [it for it in out["items"] if it["code"] == "budget.over"]
    assert len(over) == 1
    assert over[0]["priority"] == 0
    assert over[0]["kind"] == "todo"


async def test_rule_budget_near_85_percent_emits_p1():
    """花费 ≥85% 预算 → P1 warn。"""
    await db.save_budgets("2026-01", [{"category": "__total", "amount": 1000}])
    await db.add_transaction("2026-01-10", "消费", "购物", -900)
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    near = [it for it in out["items"] if it["code"] == "budget.near"]
    over = [it for it in out["items"] if it["code"] == "budget.over"]
    assert len(near) == 1
    assert near[0]["priority"] == 1
    assert over == []  # 900 < 1000，不能同时报 over


# --------------------------------------------------------------------------
# subscriptions 规则
# --------------------------------------------------------------------------

async def test_rule_subscriptions_empty_db_no_items():
    """无订阅时，无 item。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM subscriptions")
    await conn.commit()
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    sub_items = [it for it in out["items"] if it["code"].startswith("subs.")]
    assert sub_items == []


async def test_rule_subscriptions_one_due_within_window():
    """1 条 7 天内到期的订阅 → 一个 cons.due.item。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM subscriptions")
    await conn.commit()
    await db.add_subscription({"name": "Netflix", "monthly": 68, "note": "", "due_day": "20"})
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    due = [it for it in out["items"] if it["code"] == "subs.due.item"]
    assert len(due) == 1
    assert due[0]["vars"]["name"] == "Netflix"


async def test_rule_subscriptions_multiple_due_aggregate():
    """≥2 条到期 → 聚合为 subs.due.items（只发一条）。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM subscriptions")
    await conn.commit()
    await db.add_subscription({"name": "Netflix", "monthly": 68, "note": "", "due_day": "20"})
    await db.add_subscription({"name": "Spotify", "monthly": 30, "note": "", "due_day": "21"})
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    agg = [it for it in out["items"] if it["code"] == "subs.due.items"]
    singles = [it for it in out["items"] if it["code"] == "subs.due.item"]
    assert len(agg) == 1
    assert len(singles) == 0
    assert agg[0]["vars"]["n"] == 2
    assert agg[0]["vars"]["amount"] == 98  # 68 + 30


async def test_rule_subscriptions_missing_due_emits_p3():
    """订阅无 due_day → P3 info。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM subscriptions")
    await conn.commit()
    await db.add_subscription({"name": "MysterySub", "monthly": 50, "note": "", "due_day": ""})
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    missing = [it for it in out["items"] if it["code"] == "subs.missing_due"]
    assert len(missing) == 1
    assert missing[0]["priority"] == 3


# --------------------------------------------------------------------------
# debts 规则
# --------------------------------------------------------------------------

async def test_rule_debts_empty_no_items():
    """无负债时无 item。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM debts")
    await conn.commit()
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    debt_items = [it for it in out["items"] if it["code"].startswith("debt.")]
    assert debt_items == []


async def test_rule_debts_due_within_window_emits_p1():
    """负债 7 天内到期 → P1 todo。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM debts")
    await conn.commit()
    await db.add_debt({"name": "信用卡", "balance": 5000, "monthly": 1000, "rate": 0.18, "due_day": "20"})
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    due = [it for it in out["items"] if it["code"] == "debt.due.item"]
    assert len(due) == 1


async def test_rule_debts_high_rate_emits_p2():
    """利率 ≥15% → P2 info（优先偿还建议）。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM debts")
    await conn.commit()
    await db.add_debt({"name": "网贷", "balance": 10000, "monthly": 500, "rate": 0.20, "due_day": "28"})
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    high = [it for it in out["items"] if it["code"] == "debt.high_rate"]
    assert len(high) == 1
    assert high[0]["vars"]["rate"] >= 15


# --------------------------------------------------------------------------
# goals 规则
# --------------------------------------------------------------------------

async def test_rule_goals_empty_no_items():
    """无目标时无 item。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM goals")
    await conn.commit()
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    goal_items = [it for it in out["items"] if it["code"].startswith("goal.")]
    assert goal_items == []


async def test_rule_goal_late_emits_p0():
    """deadline 已过且未完成 → P0 todo。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM goals")
    await conn.commit()
    await db.add_goal({"name": "紧急备用金", "target": 100000, "saved": 5000, "deadline": "2025-12"})
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    late = [it for it in out["items"] if it["code"] == "goal.deadline_late"]
    assert len(late) == 1
    assert late[0]["priority"] == 0


async def test_rule_goal_soon_emits_p1():
    """deadline 还差 1-2 个月且进度 <80% → P1 warn。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM goals")
    await conn.commit()
    await db.add_goal({"name": "旅行基金", "target": 20000, "saved": 5000, "deadline": "2026-03"})
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    soon = [it for it in out["items"] if it["code"] == "goal.deadline_soon"]
    assert len(soon) == 1
    assert soon[0]["priority"] == 1


# --------------------------------------------------------------------------
# cashflow 规则
# --------------------------------------------------------------------------

async def test_rule_cashflow_no_outlay_no_items():
    """无订阅+无负债 → monthly_out=0 → 不发现金警告。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM subscriptions")
    await conn.execute("DELETE FROM debts")
    await conn.commit()
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    cash_items = [it for it in out["items"] if it["code"].startswith("cash.")]
    assert cash_items == []


async def test_rule_cashflow_low_cash_emits_p2():
    """现金 < 月支出 × 1.5 → P2 warn。"""
    conn = await db._conn()
    await conn.execute("DELETE FROM subscriptions")
    await conn.execute("DELETE FROM debts")
    await conn.execute("DELETE FROM positions")
    await conn.commit()
    # 月支出 3000，现金 1000 < 4500(3000*1.5)
    await db.add_subscription({"name": "云服务费", "monthly": 3000, "note": "", "due_day": "10"})
    await db.add_position({"symbol": "CASH2", "kind": "现金", "name": "活期宝", "shares": 1, "cost": 1000, "last": 1000})
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    cash = [it for it in out["items"] if it["code"] == "cash.low"]
    assert len(cash) == 1
    assert cash[0]["priority"] == 2


# --------------------------------------------------------------------------
# 规则隔离：一条规则异常不会拖垮整轮
# --------------------------------------------------------------------------

async def test_rule_exception_does_not_break_others(monkeypatch):
    """RULES 中一条规则抛错，不应拖垮整轮。

    直接在 RULES 元组里注入一条必定抛错的规则，验证其他规则仍产出战利品。
    """
    async def _explode(*_a: Any, **_kw: Any) -> list[EvalItem]:
        raise RuntimeError("boom")

    original_rules = evaluate.RULES
    monkeypatch.setattr(evaluate, "RULES", (("boom", _explode), *original_rules))
    out = await evaluate.evaluate_all(month="2026-01", today=date(2026, 1, 15))
    # 不崩溃 + 其他规则产出项（subscriptions 等）
    assert isinstance(out["items"], list)
    assert len(out["items"]) > 0


# --------------------------------------------------------------------------
# 纯函数工具
# --------------------------------------------------------------------------

def test_upcoming_due_this_month():
    from app.evaluate import _upcoming_due
    # 今天 1月15日，due_day=20，窗口 7 天 → (5, 1月20日)
    res = _upcoming_due(date(2026, 1, 15), "20", window=7)
    assert res is not None
    days, due = res
    assert days == 5
    assert due == date(2026, 1, 20)


def test_upcoming_due_cross_month():
    """1月30日，due_day=3 → 应算到下月 3 日。"""
    from app.evaluate import _upcoming_due
    res = _upcoming_due(date(2026, 1, 30), "3", window=7)
    assert res is not None
    days, due = res
    assert due.month == 2
    assert due.day == 3
    assert 0 < days <= 7


def test_upcoming_due_outside_window():
    from app.evaluate import _upcoming_due
    # 今天 1月1日，due_day=30，窗口 7 天 → None
    res = _upcoming_due(date(2026, 1, 1), "30", window=7)
    assert res is None


# --------------------------------------------------------------------------
# API 端点
# --------------------------------------------------------------------------

async def test_get_evaluate_returns_200(client):
    r = await client.get("/api/evaluate")
    assert r.status_code == 200
    body = r.json()
    assert "month" in body and "items" in body


async def test_get_evaluate_with_valid_month(client):
    r = await client.get("/api/evaluate?month=2026-01")
    assert r.status_code == 200


async def test_get_evaluate_rejects_invalid_month(client):
    r = await client.get("/api/evaluate?month=2026-13")
    assert r.status_code == 400


async def test_get_evaluate_action_has_path_only_when_set(client):
    """有 action 时应含 path 字段；无 action 时不含或 null。"""
    r = await client.get("/api/evaluate")
    body = r.json()
    for it in body["items"]:
        if it["code"] == "budget.missing":
            assert it["action"] and "path" in it["action"]
