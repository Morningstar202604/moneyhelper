"""审计与附件域：审计日志 + 附件元数据。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ._core import (
    _clamp_limit,
    _conn,
    _mark_user_data,
    fetch_all,
)
from .tenant import current_user_id

# --------------------------------------------------------------------------
# 审计日志（P2 金融级治理）
# --------------------------------------------------------------------------


async def add_audit_log(
    action: str,
    method: str,
    path: str,
    status: int,
    actor: str = "",
    detail: str = "",
    duration_ms: int = 0,
) -> dict[str, Any]:
    """写一条审计日志。action: WRITE / READ_SENSITIVE / AUTH。"""
    conn = await _conn()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    # SAVEPOINT 隔离：审计是旁路数据，不能把调用方未完成的事务一并 commit
    # （专家评审 P0-9 实测：批量入账失败时审计的 commit 会把前两条落库）。
    await conn.execute("SAVEPOINT audit_write")
    try:
        await conn.execute(
            "INSERT INTO audit_logs(user_id,ts,action,method,path,status,actor,detail,duration_ms)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                current_user_id(),
                now,
                str(action)[:20],
                str(method)[:8],
                str(path)[:200],
                int(status or 0),
                str(actor)[:64],
                str(detail)[:500],
                int(duration_ms or 0),
            ),
        )
        await conn.execute("RELEASE audit_write")
    except Exception:
        try:
            await conn.execute("ROLLBACK TO audit_write")
            await conn.execute("RELEASE audit_write")
        except Exception:  # noqa: BLE001
            pass
        raise
    return {"ok": True}


async def list_audit_logs(
    limit: int = 200, action: str | None = None
) -> list[dict[str, Any]]:
    """列审计日志（新→旧），可按类型过滤。"""
    clamped = _clamp_limit(limit, default=200)
    if action:
        rows = await fetch_all(
            "SELECT * FROM audit_logs WHERE user_id=? AND action=? ORDER BY id DESC LIMIT ?",
            (current_user_id(), str(action)[:20], clamped),
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM audit_logs WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (current_user_id(), clamped),
        )
    return rows


async def clear_audit_logs() -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute(
        "DELETE FROM audit_logs WHERE user_id=?", (current_user_id(),)
    )
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount or 0}


# --------------------------------------------------------------------------
# 附件（P2 能力扩展）
# --------------------------------------------------------------------------


async def list_attachments(limit: int = 50) -> list[dict[str, Any]]:
    rows = await fetch_all(
        "SELECT id, filename, kind, size, indexed, created_at FROM attachments"
        " WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (current_user_id(), _clamp_limit(limit)),
    )
    return rows


async def list_indexed_attachments() -> list[dict[str, Any]]:
    """已加入知识库的附件（含正文，供检索切块）。"""
    return await fetch_all(
        "SELECT id, filename, kind, content FROM attachments"
        " WHERE user_id=? AND indexed=1 AND content <> '' ORDER BY id DESC",
        (current_user_id(),),
    )


async def set_attachment_indexed(att_id: int, indexed: bool) -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute(
        "UPDATE attachments SET indexed=? WHERE user_id=? AND id=?",
        (1 if indexed else 0, current_user_id(), int(att_id)),
    )
    await conn.commit()
    if cur.rowcount == 0:
        raise ValueError("附件不存在")
    return {"ok": True, "id": int(att_id), "indexed": bool(indexed)}


async def add_attachment(
    filename: str, kind: str, size: int, content: str
) -> dict[str, Any]:
    conn = await _conn()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    cur = await conn.execute(
        "INSERT INTO attachments(user_id,filename,kind,size,content,created_at) VALUES(?,?,?,?,?,?)",
        (
            current_user_id(),
            str(filename)[:200],
            str(kind)[:20] or "text",
            int(size or 0),
            content[:6000],
            now,
        ),
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "id": cur.lastrowid}


async def get_attachment(att_id: int) -> dict[str, Any] | None:
    rows = await fetch_all(
        "SELECT * FROM attachments WHERE user_id=? AND id=?",
        (current_user_id(), int(att_id)),
    )
    return rows[0] if rows else None


async def delete_attachment(att_id: int) -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute(
        "DELETE FROM attachments WHERE user_id=? AND id=?",
        (current_user_id(), int(att_id)),
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount or 0}
