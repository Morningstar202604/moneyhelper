"""审计追踪路由：查询操作来龙去脉。

端点：
- GET /api/provenance — 按实体类型/ID 过滤查询审计记录
- GET /api/provenance/{entry_id} — 查询单条审计记录详情
"""

from __future__ import annotations

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse

from ..provenance import get_provenance_by_id, get_provenances

router = APIRouter()


@router.get("/api/provenance")
async def list_provenances(
    entity_type: str = Query(default="", description="按实体类型过滤 (position/transaction/budget/goal 等)"),
    entity_id: str = Query(default="", description="按实体 ID 过滤 (如股票代码 600519)"),
    limit: int = Query(default=50, ge=1, le=500, description="返回条数上限"),
) -> dict:
    """查询审计追踪记录。

    支持按 entity_type (实体类型) 和 entity_id (实体 ID) 过滤。
    不传过滤条件时返回最新的审计记录（默认 50 条）。
    """
    rows = await get_provenances(
        entity_type=entity_type or None,
        entity_id=entity_id or None,
        limit=limit,
    )
    return {
        "count": len(rows),
        "provenances": rows,
    }


@router.get("/api/provenance/{entry_id}")
async def get_provenance(
    entry_id: str = Path(..., description="审计记录 UUID"),
) -> dict:
    """查询单条审计记录详情。"""
    row = await get_provenance_by_id(entry_id)
    if row is None:
        return JSONResponse({"error": "审计记录不存在", "id": entry_id}, status_code=404)
    return {"provenance": row}
