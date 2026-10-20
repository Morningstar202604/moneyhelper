"""撤销域：快照记录/恢复/应用（供 main 的 undo 端点与各写入口使用）。"""
from __future__ import annotations

import json
from typing import Any

import aiosqlite

from ._core import (  # noqa: F401
    _clamp_limit,
    _conn,
    _now_iso,
    fetch_all,
)

# --------------------------------------------------------------------------
# 撤销（undo）：实体级还原（P2 金融级治理）
# --------------------------------------------------------------------------


def _row_to_json(row: aiosqlite.Row | dict[str, Any] | None) -> str:
    """快照字典序列化：None → '{}' 表示实体此前不存在（undo 时应 DELETE）。"""
    if row is None:
        return "{}"
    return json.dumps(dict(row), ensure_ascii=False, default=str)


async def _record_snapshot(
    entity: str,
    entity_id: str,
    before_json: str,
    actor: str = "",
) -> int:
    """为一次即将发生的写操作落一份前快照，供后续 undo 恢复。

    调用规范：**本函数不 commit**。上层必须在同一事务内、调用本函数继续做实际写
    操作后统一 ``await conn.commit()``——让「快照 + 写操作」原子提交，任一失败整笔回滚。

    语义：
    - before_json='{}' 代表"该实体此前不存在"，undo 时应当 DELETE 当前行；
    - before_json 为旧行 JSON 时，undo 时使用 INSERT OR REPLACE 恢复全量字段。
    """
    conn = await _conn()
    cur = await conn.execute(
        "INSERT INTO undo_records(entity,entity_id,before_json,reason,consumed_at,created_at)"
        " VALUES(?,?,?,?,?,?)",
        (
            entity,
            entity_id,
            before_json,
            actor[:500],
            "",
            _now_iso(),
        ),
    )
    return cur.lastrowid


async def _find_latest_usable_snapshot(
    conn: aiosqlite.Connection,
    entity: str,
    entity_id: str,
) -> aiosqlite.Row | None:
    """同一实体可能有多条快照，取最近一条未被撤回（consumed_at=''）的记录；没有返回 None。"""
    cur = await conn.execute(
        "SELECT * FROM undo_records"
        " WHERE entity=? AND entity_id=? AND consumed_at=''"
        " ORDER BY id DESC LIMIT 1",
        (entity, entity_id),
    )
    return await cur.fetchone()


async def _restore_from_snapshot(
    conn: aiosqlite.Connection,
    entity: str,
    entity_id: str,
    before_json: str,
) -> None:
    """按 before_json 把实体恢复成操作前状态：'{}' → DELETE，其余 → INSERT OR REPLACE。

    共享逻辑：按实体类型做列映射。所有可撤回实体都具备『单表 + 单列主键』结构，
    通过 INSERT OR REPLACE 能覆盖 update/delete 两条路径的恢复。
    """
    deleted = False
    if before_json.strip() in ("", "{}"):
        if entity == "transaction":
            await conn.execute("DELETE FROM transactions WHERE id=?", (int(entity_id),))
        elif entity == "position":
            await conn.execute("DELETE FROM positions WHERE symbol=?", (entity_id,))
        elif entity == "debt":
            await conn.execute("DELETE FROM debts WHERE name=?", (entity_id,))
        elif entity == "subscription":
            await conn.execute("DELETE FROM subscriptions WHERE name=?", (entity_id,))
        else:
            raise ValueError(f"不支持撤回的实体类型：{entity}")
        deleted = True
        _ = deleted  # 调用方如需扩展两种路径的审计日志时可直接使用
        return

    data = json.loads(before_json)
    if entity == "transaction":
        d = data.get("date")
        it = data.get("item")
        cat = data.get("category")
        amt = data.get("amount")
        if not all([d, it, cat]) or amt is None:
            raise ValueError(f"transaction 快照字段不完整：{before_json[:120]!r}")
        # owner_id 必须原样恢复：None 表示"无归属"，写成 0 会违反外键
        # （transactions.owner_id REFERENCES members(id)，members 没有 id=0）。
        owner_raw = data.get("owner_id")
        owner_id = int(owner_raw) if owner_raw not in (None, "", 0, "0") else None
        is_shared = 1 if data.get("is_shared") else 0
        await conn.execute(
            "INSERT OR REPLACE INTO transactions(id,date,item,category,amount,owner_id,is_shared)"
            " VALUES(?,?,?,?,?,?,?)",
            (int(entity_id), d, it, cat, amt, owner_id, is_shared),
        )
    elif entity == "position":
        # 任何字段缺失用 '' / 0 兜底，避免 CHECK 失败；符号一致即满足主键；符号本身不回退
        await conn.execute(
            "INSERT OR REPLACE INTO positions(symbol,name,kind,industry,shares,cost,last,buy_date,fee)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                entity_id,
                data.get("name") or "未命名",
                data.get("kind") or "股票",
                data.get("industry") or "其他",
                data.get("shares"),
                data.get("cost"),
                data.get("last"),
                data.get("buy_date"),
                data.get("fee"),
            ),
        )
    elif entity == "debt":
        await conn.execute(
            "INSERT OR REPLACE INTO debts(name,monthly,balance,rate,due_day)"
            " VALUES(?,?,?,?,?)",
            (
                entity_id,
                data.get("monthly"),
                data.get("balance"),
                data.get("rate"),
                data.get("due_day", ""),
            ),
        )
    elif entity == "subscription":
        await conn.execute(
            "INSERT OR REPLACE INTO subscriptions(name,monthly,note,due_day)"
            " VALUES(?,?,?,?)",
            (
                entity_id,
                data.get("monthly"),
                data.get("note", ""),
                data.get("due_day", ""),
            ),
        )
    else:
        raise ValueError(f"不支持撤回的实体类型：{entity}")


async def _undo_apply(record_id: int) -> dict[str, Any]:
    """对 undo_records 中一条快照执行撤回（恢复 before_json 并标记 consumed_at）。

    在单一 aiosqlite 事务里完成：
    1. 锁定该快照（空 consumed_id → 可撤回；否则幂等拒绝 → 调用方回 410 Gone）；
    2. 按 before_json 恢复实体（'' / '{}' → DELETE，否则 INSERT OR REPLACE）；
    3. 写 undo_records.consumed_at = now()。

    """
    conn = await _conn()
    # step 0: 取快照
    cur = await conn.execute("SELECT * FROM undo_records WHERE id=?", (record_id,))
    snap = await cur.fetchone()
    if snap is None:
        raise LookupError(f"undo 记录 {record_id} 不存在")
    if snap["consumed_at"]:
        raise ValueError("already_consumed")

    entity = snap["entity"]
    entity_id = snap["entity_id"]
    before_json = snap["before_json"]

    # step 1: 恢复实体
    await _restore_from_snapshot(conn, entity, entity_id, before_json)

    # step 2: 标记 consumed_at（WHERE consumed_at='' 防止 TOCTOU）
    consumed_at = _now_iso()
    cur = await conn.execute(
        "UPDATE undo_records SET consumed_at=? WHERE id=? AND consumed_at=''",
        (consumed_at, record_id),
    )
    if cur.rowcount == 0:
        # 并发消费：另一个请求已撤回此快照
        await conn.rollback()
        raise ValueError("already_consumed")
    await conn.commit()
    return {
        "ok": True,
        "id": record_id,
        "entity": entity,
        "entity_id": entity_id,
        "consumed_at": consumed_at,
    }


async def list_undo_records(
    entity: str | None = None,
    entity_id: str | None = None,
    limit: int = 200,
    include_consumed: bool = False,
) -> list[dict[str, Any]]:
    """查询撤销快照（默认只返回未被撤回的；all=True 返回全部）。

    末尾 N 条按 id DESC（最新在前），便于前端撤回面板按时间倒序展示。
    """
    sql = "SELECT * FROM undo_records WHERE 1=1"
    params: list[Any] = []
    if not include_consumed:
        sql += " AND consumed_at=''"
    if entity:
        sql += " AND entity=?"
        params.append(entity)
    if entity_id:
        sql += " AND entity_id=?"
        params.append(entity_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(_clamp_limit(limit, default=200))
    return await fetch_all(sql, tuple(params))
