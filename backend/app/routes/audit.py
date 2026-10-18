"""审计日志（provenance 之外的 audit_log 表）：查询与清空。

从 routes/system.py 拆出（M1.4 收尾）：原文件把 9 个互不相关的域塞在一起，
任何一个域的改动都要在 500+ 行里定位。
"""

from __future__ import annotations

from fastapi import APIRouter

from .. import db

router = APIRouter()


# ---------------------------------------------------------------------------
# 审计日志（P2 金融级治理）
# ---------------------------------------------------------------------------


@router.get("/api/audit")
async def audit_logs(limit: int = 200, action: str | None = None) -> dict:
    return {"audit": await db.list_audit_logs(limit, action)}


@router.post("/api/audit/clear")
async def clear_audit_logs() -> dict:
    return await db.clear_audit_logs()
