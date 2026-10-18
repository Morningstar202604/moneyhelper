"""用户认证路由：注册 / 登录 / 当前用户 / 用户数。

从 routes/system.py 拆出（M1.4 收尾）：原文件把 9 个互不相关的域塞在一起，
任何一个域的改动都要在 500+ 行里定位。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import auth, db

router = APIRouter()


# ---------------------------------------------------------------------------
# 用户认证（JWT + bcrypt）
# ---------------------------------------------------------------------------


@router.post("/api/auth/register")
async def api_register(req: auth.RegisterReq):
    return await auth.register(req)


@router.post("/api/auth/login")
async def api_login(req: auth.LoginReq, request: Request):
    return await auth.login(req, request)


@router.get("/api/auth/me")
async def api_me(user: dict = Depends(auth.require_user)):
    return await auth.me(user)


@router.get("/api/auth/user-count")
async def api_user_count():
    return {"count": await db.user_count()}
