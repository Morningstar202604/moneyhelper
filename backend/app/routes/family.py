"""家庭共享仪表板：整体汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from .. import db

router = APIRouter()


@router.get("/api/family/summary")
async def family_summary() -> dict:
    """家庭整体汇总：总收入 / 总支出 / 各成员占比 / 未结清借贷 / top 分类"""
    return await db.family_summary()
