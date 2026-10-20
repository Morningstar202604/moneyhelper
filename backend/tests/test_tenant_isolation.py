"""多租户隔离回归：两个用户的数据必须互不可见、互不覆盖。

覆盖：
1. 同一 symbol 在两个租户下可共存（复合主键）
2. 列表查询只返回当前租户数据
3. 删除/更新不会跨租户生效
4. 上下文切换后立即生效（ContextVar 语义）
"""

from __future__ import annotations

import pytest
from app import db
from app.db.tenant import LOCAL_USER_ID, current_user_id, use_user


@pytest.fixture
async def two_users(temp_db):
    """准备两个租户的持仓与流水。

    temp_db 会种入示例数据（默认租户 0），这里先清空，避免干扰"默认租户
    看不到其他租户数据"这类断言。
    """
    with use_user(LOCAL_USER_ID):
        for table in ("positions", "transactions", "subscriptions", "debts"):
            await db.execute(f"DELETE FROM {table} WHERE user_id=?", (LOCAL_USER_ID,))
    with use_user(101):
        await db.add_position(
            {"symbol": "600519", "name": "茅台A", "shares": 100, "cost": 10, "last": 12}
        )
        await db.add_transaction("2026-10-01", "用户A午餐", "餐饮", -30)
    with use_user(202):
        await db.add_position(
            {"symbol": "600519", "name": "茅台B", "shares": 5, "cost": 20, "last": 21}
        )
        await db.add_transaction("2026-10-02", "用户B打车", "交通", -50)
    yield


async def test_default_tenant_is_zero(temp_db) -> None:
    assert current_user_id() == LOCAL_USER_ID


async def test_same_symbol_coexists_across_tenants(two_users) -> None:
    """同一代码在不同租户下是两条独立持仓，互不覆盖。"""
    with use_user(101):
        a = await db.list_positions()
    with use_user(202):
        b = await db.list_positions()
    assert len(a) == 1 and len(b) == 1
    assert a[0]["name"] == "茅台A" and a[0]["shares"] == 100
    assert b[0]["name"] == "茅台B" and b[0]["shares"] == 5


async def test_transactions_isolated(two_users) -> None:
    with use_user(101):
        a = await db.list_transactions()
    with use_user(202):
        b = await db.list_transactions()
    items_a = {t["item"] for t in a}
    items_b = {t["item"] for t in b}
    assert "用户A午餐" in items_a and "用户B打车" not in items_a
    assert "用户B打车" in items_b and "用户A午餐" not in items_b


async def test_delete_does_not_cross_tenant(two_users) -> None:
    """A 删除自己的持仓，不能影响 B 的同名持仓。"""
    with use_user(101):
        await db.delete_position("600519")
        assert await db.list_positions() == []
    with use_user(202):
        rows = await db.list_positions()
        assert len(rows) == 1 and rows[0]["name"] == "茅台B"


async def test_update_does_not_cross_tenant(two_users) -> None:
    with use_user(101):
        await db.update_position({"shares": 999}, "600519")
    with use_user(202):
        rows = await db.list_positions()
        assert rows[0]["shares"] == 5, "B 的持仓被 A 的更新污染"


async def test_context_switch_restores(two_users) -> None:
    """退出 with 块后回到原租户（不污染后续请求）。"""
    assert current_user_id() == LOCAL_USER_ID
    with use_user(101):
        assert current_user_id() == 101
        with use_user(202):
            assert current_user_id() == 202
        assert current_user_id() == 101
    assert current_user_id() == LOCAL_USER_ID


async def test_default_tenant_sees_nothing_from_others(two_users) -> None:
    """默认租户（未登录）看不到任何登录用户的数据。"""
    assert await db.list_positions() == []
    assert await db.list_transactions() == []
