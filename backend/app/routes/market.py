"""行情 / 自选路由：K 线、趋势、报价、搜索、自选股管理。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import db, quotes

router = APIRouter()


@router.get("/api/kline")
async def kline(symbol: str, period: str = "daily", limit: int = 120) -> dict:
    """某标的 K 线（A股/ETF）。period: daily/weekly/monthly。"""
    try:
        out = await quotes.kline(symbol, period, max(10, min(limit, 500)))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=502)
    if not out:
        return JSONResponse({"error": f"无法获取 {symbol} 行情"}, status_code=404)
    return out


@router.get("/api/trend")
async def trend(months: int = 6) -> dict:
    return {"months": await db.monthly_trend(max(1, min(months, 24)))}


@router.get("/api/watchlist")
async def watchlist_list() -> dict:
    items = await db.list_watchlist()
    if not items:
        return {"items": []}
    qs = await asyncio.gather(*(quotes.quote_now(i["symbol"]) for i in items))
    enriched = []
    for item, q in zip(items, qs, strict=False):
        row = dict(item)
        if q:
            row.update(
                price=q["price"],
                change=q["change"],
                change_pct=q["change_pct"],
                quote_source=q["source"],
            )
        enriched.append(row)
    return {"items": enriched}


@router.post("/api/watchlist")
async def watchlist_add(payload: dict) -> dict:
    return await db.add_watchlist(
        str(payload.get("symbol", "")),
        str(payload.get("name", "")),
        str(payload.get("kind", "股票")),
    )


@router.delete("/api/watchlist/{symbol}")
async def watchlist_remove(symbol: str) -> dict:
    return await db.delete_watchlist(symbol)


@router.get("/api/quote")
async def get_quote(symbol: str) -> dict:
    q = await quotes.quote_now(symbol)
    if q is None:
        return JSONResponse({"ok": False, "error": "无法获取行情"}, status_code=404)
    return q


@router.get("/api/search")
async def search(q: str, limit: int = 8) -> dict:
    """东财 suggest：搜股票/基金/指数（仅东财源；失败返回空列表）。"""
    import os

    import httpx
    kw = q.strip()
    if not kw or len(kw) > 20:
        return {"items": []}
    token = os.getenv("EASTMONEY_SEARCH_TOKEN", "D43BF722C8E33BDC906FB84D85E326E8")
    params = {"input": kw, "type": "14", "token": token}
    headers = {
        "User-Agent": "Mozilla/5.0 (xiaoman)",
        "Referer": "https://quote.eastmoney.com/",
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                "https://searchapi.eastmoney.com/api/suggest/get",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            data = (resp.json() or {}).get("data") or {}
        rows = (data.get("QuotationCodeTable") or {}).get("Data") or []
    except Exception:  # noqa: BLE001 — 搜索失败返回空，前端提示网络不可用
        return {"items": []}
    out = []
    for r in rows[: max(1, min(limit, 20))]:
        code = str(r.get("Code") or "").strip()
        name = str(r.get("Name") or "").strip()
        if not code or not name:
            continue
        stype = str(r.get("SecurityTypeName") or "")
        kind = "基金" if "基金" in stype else ("指数" if "指" in stype else "股票")
        out.append({"symbol": code, "name": name, "kind": kind})
    return {"items": out}


@router.get("/api/subscriptions")
async def subscriptions_list() -> dict:
    """订阅列表（供前端总览页卡片使用）。"""
    items = await db.list_subscriptions()
    return {"subscriptions": items}
