"""用户认证路由：注册 / 登录 / 当前用户 / 用户数。

从 routes/system.py 拆出（M1.4 收尾）：原文件把 9 个互不相关的域塞在一起，
任何一个域的改动都要在 500+ 行里定位。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

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


# ---------------------------------------------------------------------------
# 管理员视图（方案 B：只读概览，永远不暴露其他租户的明细）
# ---------------------------------------------------------------------------


def _is_admin(user: dict) -> bool:
    return str(user.get("role") or "") == "admin"


@router.get("/api/auth/users")
async def api_users(user: dict = Depends(auth.require_user)) -> dict:
    """账号列表（仅管理员）。不含密码哈希，也不含任何业务数据。"""
    if not _is_admin(user):
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    rows = await db.user_list()
    return {"users": rows, "count": len(rows)}


@router.get("/api/auth/tenants-overview")
async def api_tenants_overview(user: dict = Depends(auth.require_user)) -> dict:
    """各租户的数据规模（仅管理员）。

    设计取舍：只给条数，不给金额/名称/流水内容。
    管理员需要回答的是"这个实例有多少人在用、各自多少数据"，
    而不是"张三这个月花了多少钱"——后者属于租户隐私，家庭共享场景
    已有 members 机制承载，不需要在账号层开一个后门。
    """
    if not _is_admin(user):
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)
    counts = await db.counts_by_tenant()
    users = await db.user_list()
    overview = []
    for u in users:
        uid = int(u["id"])
        row = counts.get(uid, {})
        overview.append(
            {
                "user_id": uid,
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
                "disabled": bool(u["disabled"]),
                "counts": {
                    "positions": row.get("positions", 0),
                    "transactions": row.get("transactions", 0),
                    "goals": row.get("goals", 0),
                    "memory": row.get("user_memory", 0),
                    "runs": row.get("runs", 0),
                },
            }
        )
    return {"tenants": overview, "count": len(overview)}
