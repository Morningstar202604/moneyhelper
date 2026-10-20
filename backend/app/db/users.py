"""用户体系：注册/查询/密码校验/登录时间。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ._core import (
    _conn,
    fetch_all,
)

# --------------------------------------------------------------------------
# 用户体系（多租户基础）
# --------------------------------------------------------------------------


async def user_create(
    username: str, password: str, display_name: str = "", role: str = "user"
) -> int:
    """创建用户，返回行 id。username 唯一；密码 bcrypt 哈希。"""
    from passlib.hash import bcrypt

    pw_hash = bcrypt.using(rounds=12).hash(password)
    conn = await _conn()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    cur = await conn.execute(
        "INSERT INTO users(username, password_hash, display_name, role, created_at) "
        "VALUES(?,?,?,?,?)",
        (username, pw_hash, display_name or username, role, now),
    )
    await conn.commit()
    return cur.lastrowid


async def user_get_by_username(username: str) -> dict[str, Any] | None:
    conn = await _conn()
    cur = await conn.execute(
        "SELECT id, username, password_hash, display_name, role, disabled, last_login, created_at "
        "FROM users WHERE username=?",
        (username,),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def user_get(uid: int) -> dict[str, Any] | None:
    conn = await _conn()
    cur = await conn.execute(
        "SELECT id, username, password_hash, display_name, role, disabled, last_login, created_at "
        "FROM users WHERE id=?",
        (uid,),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def user_verify_password(user: dict[str, Any], password: str) -> bool:
    from passlib.hash import bcrypt

    try:
        return bcrypt.verify(password, user["password_hash"])
    except Exception:
        return False


async def user_update_last_login(uid: int) -> None:
    conn = await _conn()
    await conn.execute(
        "UPDATE users SET last_login=? WHERE id=?",
        (datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), uid),
    )
    await conn.commit()


async def user_count() -> int:
    conn = await _conn()
    cur = await conn.execute("SELECT COUNT(*) AS n FROM users WHERE disabled=0")
    row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def user_list() -> list[dict[str, Any]]:
    """列出所有用户（只给管理员用的账号视图，不含密码哈希）。"""
    return await fetch_all(
        "SELECT id, username, display_name, role, disabled, last_login, created_at"
        " FROM users ORDER BY id"
    )


async def counts_by_tenant() -> dict[int, dict[str, int]]:
    """各租户的数据条数概览（只给管理员看规模，不暴露任何明细）。

    这是"管理员可见范围"的边界：条数能回答"这个实例有多少人在用、各自多少数据"，
    但不含金额、名称、流水内容——避免把隐私能力做成后门。
    """
    tables = ("positions", "transactions", "goals", "user_memory", "runs")
    out: dict[int, dict[str, int]] = {}
    for table in tables:
        rows = await fetch_all(
            f"SELECT user_id, COUNT(*) AS n FROM {table} GROUP BY user_id"
        )
        for row in rows:
            uid = int(row["user_id"])
            out.setdefault(uid, {})
            out[uid][table] = int(row["n"])
    return out
