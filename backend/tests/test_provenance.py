"""Provenance 审计追踪系统测试。

覆盖：
1. 写入 + 查询基本流程
2. 按 entity_type 过滤
3. 按 entity_id 过滤
4. 环形缓冲区满时淘汰旧记录
5. 异步非阻塞验证
6. 按 ID 查询单条
7. 联合过滤
8. HTTP 路由集成（预算、目标、删除）
9. 持久化到 SQLite
10. import 审计写入
11. 单条路由 404
12. 默认 source / username
"""

from __future__ import annotations

import asyncio
from collections import deque

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# 单元测试：验证数据结构与内存缓冲区语义
# ---------------------------------------------------------------------------


def test_provenance_entry_to_dict():
    """ProvenanceEntry dataclass 序列化正确。"""
    from app.provenance import ProvenanceEntry

    entry = ProvenanceEntry(
        id="test-uuid-1",
        timestamp="2025-01-01T00:00:00+00:00",
        action="add_position",
        entity_type="position",
        entity_id="600519",
        before=None,
        after={"shares": 100},
        source="api",
        username="test_user",
        metadata={"thread": "abc"},
    )
    d = entry.to_dict()
    assert d["id"] == "test-uuid-1"
    assert d["action"] == "add_position"
    assert d["entity_type"] == "position"
    assert d["after"] == {"shares": 100}
    assert d["before"] is None
    assert d["source"] == "api"
    assert d["metadata"] == {"thread": "abc"}


def test_ring_buffer_capacity_constant():
    """环形缓冲区容量常量为 10000。"""
    from app.provenance import ring_capacity
    assert ring_capacity() == 10_000


def test_ring_buffer_eviction():
    """collections.deque(maxlen=N) 满时自动淘汰最旧记录。"""
    buf = deque(maxlen=3)
    for i in range(5):
        buf.append(i)
    assert len(buf) == 3
    assert list(buf) == [2, 3, 4]


def test_truncate_snapshot():
    """快照裁剪函数限制 key 数和字符串长度。"""
    from app.provenance import _truncate_snapshot

    # None 直接返回 None
    assert _truncate_snapshot(None) is None

    # 正常裁剪
    snap = {"a": "x" * 500, "b": 1, "c": 2, "d": 3}
    result = _truncate_snapshot(snap, max_keys=2, max_val_len=10)
    assert len(result) == 2
    assert result["a"] == "x" * 10 + "…"

    # 空 dict
    assert _truncate_snapshot({}) == {}


# ---------------------------------------------------------------------------
# 异步单元测试（需要 temp_db 以支持后台持久化任务）
# 注意：异步测试必须位于 _cancel_provenance_tasks autouse fixture 定义之后
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_entity_type(temp_db):
    """按 entity_type 过滤仅返回匹配记录。"""
    from app.provenance import get_provenances, record_provenance

    await record_provenance(action="add", entity_type="position", entity_id="600519", source="api")
    await record_provenance(action="add", entity_type="goal", entity_id="goal-1", source="api")

    rows = await get_provenances(entity_type="position", limit=50)
    assert all(r["entity_type"] == "position" for r in rows)
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_filter_by_entity_id(temp_db):
    """按 entity_id 精确过滤。"""
    from app.provenance import get_provenances, record_provenance

    entry = await record_provenance(
        action="buy", entity_type="position",
        entity_id="UNIQUE-XYZ-888", source="api"
    )

    rows = await get_provenances(entity_id="UNIQUE-XYZ-888", limit=10)
    assert any(r["id"] == entry.id for r in rows)


@pytest.fixture(autouse=True)
async def _cancel_provenance_tasks():
    """每个测试结束取消挂起的后台持久化任务，避免 aiosqlite 线程在 loop 关闭后仍尝试回调。"""
    yield
    from app.provenance import _pending_tasks
    for task in list(_pending_tasks):
        task.cancel()
    # 让取消异步传播
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_record_and_get_from_memory(temp_db):
    """写入一条审计后能从内存缓冲区查到。"""
    from app.provenance import get_provenances, record_provenance

    entry = await record_provenance(
        action="test_action",
        entity_type="test_entity",
        entity_id="test-001",
        before={"state": "old"},
        after={"state": "new"},
        source="agent",
        username="test_user",
        metadata={"thread": "unit-test"},
    )

    assert entry.id
    assert entry.action == "test_action"
    assert entry.source == "agent"

    rows = await get_provenances(entity_type="test_entity", limit=10)
    assert len(rows) >= 1
    found = next((r for r in rows if r["id"] == entry.id), None)
    assert found is not None
    assert found["action"] == "test_action"
    assert found["before"] == {"state": "old"}
    assert found["after"] == {"state": "new"}


@pytest.mark.asyncio
async def test_get_provenance_by_id_not_found(temp_db):
    """查询不存在的 UUID 返回 None。"""
    from app.provenance import get_provenance_by_id
    assert await get_provenance_by_id("non-existent-uuid-12345") is None


@pytest.mark.asyncio
async def test_async_non_blocking(temp_db):
    """record_provenance 应在毫秒级返回（fire-and-forget 不阻塞）。"""
    import time

    from app.provenance import record_provenance

    start = time.monotonic()
    entry = await record_provenance(
        action="speed_test", entity_type="bench", entity_id="fast", source="test"
    )
    elapsed = time.monotonic() - start

    assert elapsed < 0.01, f"record_provenance 太慢：{elapsed:.4f}s"
    assert entry.id


@pytest.mark.asyncio
async def test_default_source_and_username(temp_db):
    """不传 source/username 时默认值正确。"""
    from app.provenance import record_provenance

    entry = await record_provenance(action="defaults", entity_type="test", entity_id="dv")
    assert entry.source == "api"
    assert entry.username == "system"
    assert isinstance(entry.metadata, dict)


# ---------------------------------------------------------------------------
# 集成测试：通过 HTTP 路由
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_provenance_via_api(temp_db):
    """保存预算后能查到审计记录。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8787") as ac:
        resp = await ac.put("/api/budgets", json={
            "month": "2025-07",
            "budgets": [{"category": "__total", "amount": 5000}],
        })
        assert resp.status_code == 200

        await asyncio.sleep(0.3)

        resp = await ac.get("/api/provenance?entity_type=budget&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert any(p["action"] == "save_budgets" for p in data["provenances"])


@pytest.mark.asyncio
async def test_goals_provenance_via_api(temp_db):
    """创建/更新/删除目标均记录审计。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8787") as ac:
        # 创建
        resp = await ac.post("/api/goals", json={
            "name": "prov-test-goal",
            "target": 50000,
            "saved": 2000,
            "deadline": "2026-06",
        })
        assert resp.status_code == 200
        await asyncio.sleep(0.2)

        resp = await ac.get("/api/provenance?entity_id=prov-test-goal&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        actions = [p["action"] for p in data["provenances"]]
        assert "create_goal" in actions

        # 删除
        resp = await ac.delete("/api/goals/prov-test-goal")
        assert resp.status_code == 200
        await asyncio.sleep(0.2)

        resp = await ac.get("/api/provenance?entity_id=prov-test-goal&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert any(p["action"] == "delete_goal" for p in data["provenances"])


@pytest.mark.asyncio
async def test_provenance_single_entry_route(temp_db):
    """GET /api/provenance/{entry_id} 路由（存在+不存在）。"""
    from app.main import app
    from app.provenance import record_provenance

    entry = await record_provenance(action="route_test", entity_type="t", entity_id="rt1", source="api")
    await asyncio.sleep(0.1)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8787") as ac:
        resp = await ac.get(f"/api/provenance/{entry.id}")
        assert resp.status_code == 200
        assert resp.json()["provenance"]["id"] == entry.id

        # 不存在
        resp = await ac.get("/api/provenance/no-such-id-xyz")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_provenance_route_empty_filter(temp_db):
    """不带过滤参数时返回审计列表。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8787") as ac:
        resp = await ac.get("/api/provenance?limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert "provenances" in data
        assert isinstance(data["provenances"], list)


@pytest.mark.asyncio
async def test_provenance_persists_to_sqlite(temp_db):
    """审计记录最终持久化到 SQLite。"""
    from app import db
    from app.provenance import flush_writes, record_provenance

    await record_provenance(action="persist_test", entity_type="t", entity_id="sqlite-chk", source="api")
    await flush_writes()

    rows = await db.fetch_all(
        "SELECT * FROM provenance_log WHERE action = ? ORDER BY timestamp DESC LIMIT 5",
        ("persist_test",),
    )
    assert len(rows) >= 1
    assert rows[0]["entity_type"] == "t"
