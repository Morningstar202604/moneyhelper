"""负债与订阅域。"""
from __future__ import annotations

from typing import Any

from ._core import (
    _clean_due_day,
    _conn,
    _mark_user_data,
)
from .undo import _record_snapshot, _row_to_json


async def add_debt(d: dict[str, Any]) -> dict[str, Any]:
    conn = await _conn()
    clean = {
        "name": str(d.get("name", "")).strip(),
        "monthly": float(d.get("monthly", 0) or 0),
        "balance": float(d.get("balance", 0) or 0),
        "rate": float(d.get("rate", 0) or 0),
        "due_day": _clean_due_day(d.get("due_day", "")),
    }
    if not clean["name"]:
        raise ValueError("名称不能为空")
    # 撤销快照：upsert 前的状态（已存在=旧行，新增='{}'）
    existing = await (
        await conn.execute("SELECT * FROM debts WHERE name=?", (clean["name"],))
    ).fetchone()
    await _record_snapshot("debt", clean["name"], _row_to_json(existing))
    await conn.execute(
        "INSERT INTO debts(name,monthly,balance,rate,due_day) VALUES(:name,:monthly,:balance,:rate,:due_day)"
        " ON CONFLICT(name) DO UPDATE SET monthly=excluded.monthly,"
        " balance=excluded.balance, rate=excluded.rate, due_day=excluded.due_day",
        clean,
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "name": clean["name"]}


async def delete_debt(name: str) -> dict[str, Any]:
    conn = await _conn()
    # 撤销快照：记录删除前的完整旧行，撤回时 INSERT OR REPLACE 恢复
    old = await (
        await conn.execute("SELECT * FROM debts WHERE name=?", (name,))
    ).fetchone()
    if old is None:
        return {"ok": False, "deleted": 0}
    await _record_snapshot("debt", name, _row_to_json(old))
    cur = await conn.execute("DELETE FROM debts WHERE name=?", (name,))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


async def add_subscription(s: dict[str, Any]) -> dict[str, Any]:
    conn = await _conn()
    clean = {
        "name": str(s.get("name", "")).strip(),
        "monthly": float(s.get("monthly", 0) or 0),
        "note": str(s.get("note", "")).strip(),
        "due_day": _clean_due_day(s.get("due_day", "")),
    }
    if not clean["name"]:
        raise ValueError("名称不能为空")
    if clean["monthly"] <= 0:
        raise ValueError("月支出需大于 0")
    # 撤销快照：upsert 前的状态（已存在=旧行，新增='{}'）
    existing = await (
        await conn.execute("SELECT * FROM subscriptions WHERE name=?", (clean["name"],))
    ).fetchone()
    await _record_snapshot("subscription", clean["name"], _row_to_json(existing))
    await conn.execute(
        "INSERT INTO subscriptions(name,monthly,note,due_day) VALUES(:name,:monthly,:note,:due_day)"
        " ON CONFLICT(name) DO UPDATE SET monthly=excluded.monthly,"
        " note=excluded.note, due_day=excluded.due_day",
        clean,
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "name": clean["name"]}


async def delete_subscription(name: str) -> dict[str, Any]:
    conn = await _conn()
    # 撤销快照：记录删除前的完整旧行，撤回时 INSERT OR REPLACE 恢复
    old = await (
        await conn.execute("SELECT * FROM subscriptions WHERE name=?", (name,))
    ).fetchone()
    if old is None:
        return {"ok": False, "deleted": 0}
    await _record_snapshot("subscription", name, _row_to_json(old))
    cur = await conn.execute("DELETE FROM subscriptions WHERE name=?", (name,))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}
