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


@router.post("/api/budgets/suggest")
async def suggest_budgets() -> dict:
    """AI 按近两月实际支出给月度预算建议（只产出建议不落库；未接模型时友好报错）。"""
    from datetime import datetime, timedelta

    from .. import llm

    if not await llm.llm_available():
        return {"ok": False, "error": "未接入模型 —— 先到「设置 → AI 回答」配置模型端点"}

    # 近 60 天支出按类别聚合（只统计支出：amount < 0）
    txns = await db.list_transactions()
    cutoff = (datetime.now().astimezone().date() - timedelta(days=60)).isoformat()
    by_cat: dict[str, float] = {}
    total = 0.0
    for t in txns:
        d = str(t.get("date") or "")
        amt = float(t.get("amount") or 0)
        if d >= cutoff and amt < 0:
            cat = str(t.get("category") or "其他")
            by_cat[cat] = by_cat.get(cat, 0.0) + abs(amt)
            total += abs(amt)
    if total <= 0:
        return {"ok": False, "error": "近两个月没有支出记录，先记几笔再来"}

    summary = (
        "近约两个月（60 天）实际支出分类汇总（元）："
        + "，".join(f"{k} {round(v)}" for k, v in sorted(by_cat.items(), key=lambda x: -x[1])[:15])
        + f"。总支出 {round(total)} 元。"
    )
    system = (
        "你是理财预算顾问。根据用户近两月支出明细，给出下个月预算建议。只输出 JSON："
        '{"total": 整数, "categories": {"分类名": 整数}}。'
        "规则：分类名沿用输入中的中文名；金额取整；建议值贴近实际并留一点余量；分类不超过 8 个。"
    )
    out = await llm.json_complete(system, summary, timeout=25.0)
    if not isinstance(out, dict):
        return {"ok": False, "error": "生成失败，请稍后重试"}
    try:
        total_v = int(float(out.get("total") or 0))
        cats = {
            str(k)[:12]: int(float(v))
            for k, v in (out.get("categories") or {}).items()
            if float(v or 0) > 0
        }
    except (TypeError, ValueError):
        return {"ok": False, "error": "生成结果不可用，请重试"}
    if total_v <= 0 or not cats:
        return {"ok": False, "error": "生成结果不可用，请重试"}
    return {
        "ok": True,
        "suggestion": {"total": total_v, "categories": cats},
        "based_on": {"days": 60, "spent": round(total)},
    }
