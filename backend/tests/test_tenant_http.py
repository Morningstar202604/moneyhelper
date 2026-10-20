"""HTTP 级多租户隔离：两个真实 JWT 用户通过 API 读写，数据必须互不可见。

与 test_tenant_isolation.py 的区别：那一组直接调数据层验证 SQL 过滤；
这一组走真实 HTTP 链路（中间件解析 JWT → 写入租户上下文 → 路由 → 数据层），
验证"登录用户看到的只有自己的数据"这一端到端承诺。
"""

from __future__ import annotations

import pytest
from app import auth, db
from httpx import ASGITransport, AsyncClient


async def _make_user(username: str) -> tuple[int, str]:
    """创建用户并返回 (user_id, jwt)。

    直接插入用户行而不走 user_create：本组测试只关心租户隔离，
    不验证口令哈希（passlib 与 bcrypt>=4 的版本噪声会干扰，另有用例覆盖）。
    """
    conn = await db._conn()
    await conn.execute(
        "INSERT INTO users(username, password_hash, display_name, role, created_at)"
        " VALUES(?,?,?,?,datetime('now'))",
        (username, "x", username, "user"),
    )
    await conn.commit()
    user = await db.user_get_by_username(username)
    assert user is not None
    token = auth._make_jwt(user)  # noqa: SLF001 — 测试直接签发，跳过登录限流
    return int(user["id"]), token


@pytest.fixture
async def client(temp_db):
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1:8787"
    ) as c:
        yield c


async def _add_position(c: AsyncClient, token: str, symbol: str, name: str, shares: int) -> None:
    r = await c.post(
        "/api/positions",
        json={"symbol": symbol, "name": name, "shares": shares, "cost": 10, "last": 12},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text


async def _positions(c: AsyncClient, token: str) -> list[dict]:
    """持仓列表走 /api/dashboard（没有独立的 GET /api/positions）。"""
    r = await c.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json().get("positions") or []


async def test_two_users_see_only_their_positions(client: AsyncClient) -> None:
    _, token_a = await _make_user("alice")
    _, token_b = await _make_user("bob")

    # 同一代码两人都能持有（复合主键，不再互相覆盖）
    await _add_position(client, token_a, "600519", "茅台的A", 100)
    await _add_position(client, token_b, "600519", "茅台的B", 5)

    a = await _positions(client, token_a)
    b = await _positions(client, token_b)
    assert [(p["name"], p["shares"]) for p in a] == [("茅台的A", 100)]
    assert [(p["name"], p["shares"]) for p in b] == [("茅台的B", 5)]


async def test_user_cannot_see_other_transactions(client: AsyncClient) -> None:
    _, token_a = await _make_user("carol")
    _, token_b = await _make_user("dave")

    await client.post(
        "/api/transactions",
        json={"date": "2026-10-01", "item": "carol的午餐", "category": "餐饮", "amount": -30},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    await client.post(
        "/api/transactions",
        json={"date": "2026-10-02", "item": "dave的打车", "category": "交通", "amount": -50},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    ra = await client.get("/api/transactions", headers={"Authorization": f"Bearer {token_a}"})
    rb = await client.get("/api/transactions", headers={"Authorization": f"Bearer {token_b}"})
    items_a = {t["item"] for t in (ra.json().get("transactions") or ra.json())}
    items_b = {t["item"] for t in (rb.json().get("transactions") or rb.json())}
    assert "carol的午餐" in items_a and "dave的打车" not in items_a
    assert "dave的打车" in items_b and "carol的午餐" not in items_b


async def test_goals_isolated(client: AsyncClient) -> None:
    _, token_a = await _make_user("erin")
    _, token_b = await _make_user("frank")

    await client.post(
        "/api/goals",
        json={"name": "买房", "target": 100000, "saved": 1000},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    def _names(payload) -> set[str]:
        rows = payload.get("goals") if isinstance(payload, dict) else payload
        return {str(g.get("name")) for g in (rows or []) if isinstance(g, dict)}

    ta = (await client.get("/api/goals", headers={"Authorization": f"Bearer {token_a}"})).json()
    tb = (await client.get("/api/goals", headers={"Authorization": f"Bearer {token_b}"})).json()
    names_a = _names(ta)
    names_b = _names(tb)
    assert "买房" in names_a
    assert "买房" not in names_b, "B 看到了 A 的目标"


async def test_no_token_sees_default_tenant_only(client: AsyncClient) -> None:
    """未登录（无 JWT）请求落在默认租户，看不到任何登录用户的数据。"""
    _, token_a = await _make_user("grace")
    await _add_position(client, token_a, "000001", "平安A", 7)

    anon = await client.get("/api/dashboard")
    assert anon.status_code == 200
    rows = anon.json().get("positions") or []
    assert not any(p.get("name") == "平安A" for p in rows)
