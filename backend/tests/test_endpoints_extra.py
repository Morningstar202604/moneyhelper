"""两个新薄端点的测试：GET /api/subscriptions + GET /api/undoables + delete_memory_by_kind 辅助。"""

from __future__ import annotations

import pytest
from app import db


@pytest.mark.anyio
async def test_list_subscriptions_endpoint_via_app(temp_db):
    from app import main
    from starlette.testclient import TestClient

    # 注入 app 状态（main.app 的 limiter 可能启用；测试用 conftenv off）
    with TestClient(main.app) as c:
        r = c.get("/api/subscriptions")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "subscriptions" in data
        assert isinstance(data["subscriptions"], list)


@pytest.mark.anyio
async def test_undoables_endpoint_returns_snapshot_labels(temp_db):
    from app import main
    from starlette.testclient import TestClient

    db2 = db
    await db2.add_transaction("2026-10-05", "测试流水", "测试", -10.0)
    await db2.add_subscription({"name": "sub1", "monthly": 30.0, "due_day": "10"})

    with TestClient(main.app) as c:
        r = c.get("/api/undoables?limit=5")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body
        # 至少订阅 add 会有一条快照
        ents = [it["entity"] for it in body["items"]]
        assert "subscription" in ents or "transaction" in ents


@pytest.mark.anyio
async def test_delete_memory_by_kind(temp_db):
    await db.add_memory("kind-A record 1", kind="kind-A")
    await db.add_memory("kind-A record 2", kind="kind-A")
    await db.add_memory("kind-B record", kind="kind-B")

    res = await db.delete_memory_by_kind("kind-A")
    assert res["ok"] is True
    assert res["deleted"] == 2

    leftover = await db.fetch_all("SELECT kind FROM user_memory")
    assert all(r["kind"] == "kind-B" for r in leftover)

    # kind 为空不删
    bad = await db.delete_memory_by_kind("")
    assert bad["ok"] is False
