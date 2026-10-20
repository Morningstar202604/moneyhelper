"""财务目标域 CRUD。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ._core import (
    _conn,
    _mark_user_data,
    fetch_all,
)

# --------------------------------------------------------------------------
# 财务目标（goals）
# --------------------------------------------------------------------------


async def list_goals() -> list[dict[str, Any]]:
    """当前租户的目标列表。"""
    from .tenant import current_user_id

    return await fetch_all(
        "SELECT * FROM goals WHERE user_id=? ORDER BY created_at DESC, name",
        (current_user_id(),),
    )


async def add_goal(g: dict[str, Any]) -> dict[str, Any]:
    """新增目标。字段：name / target / saved（可选）/ deadline（可选，YYYY-MM）。"""
    name = str(g.get("name") or "").strip()[:40]
    if not name:
        raise ValueError("目标名称必填")
    try:
        target = float(g.get("target", 0) or 0)
    except (TypeError, ValueError):
        raise ValueError("目标金额不合法") from None
    if target <= 0:
        raise ValueError("目标金额需大于 0")
    try:
        saved = max(0.0, float(g.get("saved", 0) or 0))
    except (TypeError, ValueError):
        saved = 0.0
    deadline = str(g.get("deadline") or "").strip()[:7]
    from .tenant import current_user_id

    conn = await _conn()
    await conn.execute(
        "INSERT INTO goals(user_id,name,target,saved,deadline,created_at)"
        " VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET"
        " target=excluded.target, saved=excluded.saved, deadline=excluded.deadline",
        (
            current_user_id(),
            name,
            target,
            saved,
            deadline,
            datetime.now().astimezone().isoformat(timespec="seconds"),
        ),
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {
        "ok": True,
        "name": name,
        "target": target,
        "saved": saved,
        "deadline": deadline,
    }


async def update_goal(name: str, patch: dict[str, Any]) -> dict[str, Any]:
    """更新目标的部分字段（target/saved/deadline）。"""
    name = str(name or "").strip()
    if not name:
        raise ValueError("目标名称必填")
    fields: list[str] = []
    params: list[Any] = []
    for key in ("target", "saved", "deadline"):
        if key not in patch:
            continue
        if key == "deadline":
            v = str(patch[key] or "").strip()[:7]
        else:
            try:
                v = float(patch[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} 不合法") from None
            if key == "target" and v <= 0:
                raise ValueError("目标金额需大于 0")
            if key == "saved":
                v = max(0.0, v)
        fields.append(f"{key}=?")
        params.append(v)
    if not fields:
        raise ValueError("没有可更新的字段")
    from .tenant import current_user_id

    conn = await _conn()
    cur = await conn.execute(
        f"UPDATE goals SET {', '.join(fields)} WHERE user_id=? AND name=?",
        [*params, current_user_id(), name],
    )
    await _mark_user_data(conn)
    await conn.commit()
    if cur.rowcount == 0:
        raise ValueError("目标不存在")
    return {"ok": True, "name": name}


async def delete_goal(name: str) -> dict[str, Any]:
    from .tenant import current_user_id

    conn = await _conn()
    cur = await conn.execute(
        "DELETE FROM goals WHERE user_id=? AND name=?", (current_user_id(), name)
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}
