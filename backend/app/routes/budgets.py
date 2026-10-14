"""预算路由：查询 + 更新月度预算设置。"""

from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import db
from ..provenance import record_provenance

router = APIRouter()


def _current_month() -> str:
    from datetime import datetime
    return datetime.now().astimezone().strftime("%Y-%m")


@router.get("/api/budgets")
async def get_budgets(month: str | None = None) -> dict:
    """返回指定月（默认本月）的预算设置 + 实时使用情况。"""
    m = (month or "").strip() or _current_month()
    if not re.fullmatch(r"(20\d{2}|19\d{2})-(0[1-9]|1[0-2])", m):
        return JSONResponse({"error": "月份需为 YYYY-MM（01–12）"}, status_code=400)
    rows = await db.list_budgets(m)
    budgets = [
        {
            "category": "总预算" if r["category"] == "__total" else r["category"],
            "key": r["category"],
            "amount": r["amount"],
        }
        for r in rows
    ]
    return {
        "month": m,
        "budgets": budgets,
        "usage": await db.budget_usage(m),
    }


@router.put("/api/budgets")
async def put_budgets(payload: dict) -> dict:
    month = (payload or {}).get("month") or _current_month()
    if not re.fullmatch(r"(20\d{2}|19\d{2})-(0[1-9]|1[0-2])", month):
        return JSONResponse({"error": "月份需为 YYYY-MM（01–12）"}, status_code=400)
    items = (payload or {}).get("budgets")
    if not isinstance(items, list):
        return JSONResponse({"error": "budgets 需为数组"}, status_code=400)
    clean_map: dict[str, float] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            amt = float(it.get("amount", 0) or 0)
        except (TypeError, ValueError):
            return JSONResponse({"error": "预算金额不合法"}, status_code=400)
        if amt > 0:
            # 同分类后一项覆盖前一项（upsert 语义），避免主键冲突
            clean_map[str(it.get("category", "__total"))] = amt
    clean = [{"category": k, "amount": v} for k, v in clean_map.items()]
    # 操作前快照：已有预算
    before = {r["category"]: r["amount"] for r in await db.list_budgets(month)}
    await db.save_budgets(month, clean)
    # 异步记录审计（不阻塞主业务）
    after = {r["category"]: r["amount"] for r in await db.list_budgets(month)}
    await record_provenance(
        action="save_budgets",
        entity_type="budget",
        entity_id=month,
        before=before,
        after=after,
        source="api",
        username="system",
    )
    return {"ok": True, "month": month, "count": len(clean)}
