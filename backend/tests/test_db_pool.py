"""M1.3 读连接池回归：并发读不串数据、读写隔离、close_db 清池。"""
from __future__ import annotations

import asyncio


async def test_concurrent_reads_consistent(temp_db):
    """30 并发读同一批行，结果集必须一致（读池轮询复用不丢行）。"""
    from app import db

    for i in range(10):
        await db.add_transaction("2026-01-01", f"item{i}", "餐饮", -(i + 1))

    async def snap() -> set:
        rows = await db.fetch_all("SELECT item FROM transactions WHERE category='餐饮'")
        return {r["item"] for r in rows}

    results = await asyncio.gather(*(snap() for _ in range(30)))
    expected = {f"item{i}" for i in range(10)}
    # temp_db 种子含示例餐饮行（外卖餐饮/聚餐等）：断言本测试写入的 10 条全员在场 + 各快照一致
    assert all(expected <= r for r in results), "并发读必须全员看到完整结果集"
    assert len({tuple(sorted(r)) for r in results}) == 1, "各连接快照必须一致"


async def test_write_then_read_visible(temp_db):
    """写连接提交后，读池连接立即可见（WAL 快照语义）。"""
    from app import db

    # 先用读池建立连接（惰性建连路径）
    await db.fetch_all("SELECT count(*) AS n FROM transactions")
    await db.add_transaction("2026-02-02", "压测写入", "餐饮", -99.0)
    rows = await db.fetch_all("SELECT * FROM transactions WHERE item='压测写入'")
    assert len(rows) == 1


async def test_close_db_clears_read_pool(temp_db):
    """close_db 必须清空读池，防止跨测试/跨库残留连接。"""
    from app import db
    from app.db import _core

    await db.fetch_all("SELECT count(*) AS n FROM transactions")
    assert len(_core._read_conns) > 0
    await db.close_db()
    assert _core._read_conns == []
