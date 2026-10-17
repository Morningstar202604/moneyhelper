"""用户体系：注册/查询/密码校验/登录时间。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ._core import (
    _conn,
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
