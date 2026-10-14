"""MCP Server：把小满所有工具暴露为标准 MCP 协议。

通过 fastmcp 把 tools.py 里的工具包装成 MCP 工具，让任何支持 MCP Client 的 AI IDE
（Claude Code / Cursor / Windsurf / Cline 等）都能直接调用小满的工具集：
- 持仓分析、账本查询、风控、预算、目标、K线 等财务工具
- search_symbol / get_quote / add_to_watchlist 等行情工具
- get_now / web_search 等通用工具

启动方式：
1. 嵌入 FastAPI（默认）：mount 到 /mcp 路径，与主应用同进程
2. 独立进程：python -m app.mcp_server（stdio transport，供 Claude Desktop 接入）

MCP 协议接入后，Claude Code / Cursor 等 IDE 可以直接对小满数据库执行财务分析。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from . import db
from . import tools as xtools
from .logging_utils import get_logger
from .provenance import record_provenance

log = get_logger(__name__)

# MCP Server：fastmcp 版本与 FastAPI 版本可能冲突，import 失败就降级 no-op
try:
    from fastmcp import FastMCP
    mcp = FastMCP("xiaoman-finance")
    MCP_AVAILABLE = True
except Exception as e:  # pragma: no cover
    log.warning("mcp.fastmcp_unavailable: %s — MCP server disabled", e)
    # 假装饰器：让 @mcp.tool() / @mcp.resource() 等不炸，函数原样返回
    class _FakeMCP:
        def tool(self, *a, **kw):
            def deco(fn): return fn
            return deco
        def resource(self, *a, **kw):
            def deco(fn): return fn
            return deco
        def prompt(self, *a, **kw):
            def deco(fn): return fn
            return deco
        def sse_app(self):
            raise RuntimeError("MCP unavailable")
    mcp = _FakeMCP()
    MCP_AVAILABLE = False


# ---------------------------------------------------------------------------
# 持仓 / 组合分析工具
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_market_view() -> str:
    """查询用户持仓组合：总市值、累计盈亏、前几大持仓、集中度告警。"""
    return await xtools.tool_get_market_view({})


@mcp.tool()
async def get_ledger_view() -> str:
    """查询用户账本：本月收入、支出、结余、储蓄率、支出分类、订阅、负债、应急金。"""
    return await xtools.tool_get_ledger_view({})


@mcp.tool()
async def get_risk_flags() -> str:
    """运行风控规则：集中度超限、应急金不足、高息负债、负债收入比偏高、储蓄率偏低等告警。"""
    return await xtools.tool_get_risk_flags({})


@mcp.tool()
async def get_budget(month: str = "") -> str:
    """查询预算设置与实时使用情况。month 格式 YYYY-MM，省略=本月。"""
    return await xtools.tool_get_budget({"month": month})


@mcp.tool()
async def get_trend(months: int = 6) -> str:
    """查询近几个月收支趋势。months 范围 1-24，默认 6。"""
    return await xtools.tool_get_trend({"months": months})


@mcp.tool()
async def get_goals() -> str:
    """查询用户的财务目标：目标金额、已存金额、进度百分比、距截止月、建议月存。"""
    return await xtools.tool_get_goals({})


@mcp.tool()
async def get_health_check() -> str:
    """跑一次结构化财务体检：资产配置 / 现金流 / 负债 / 应急金 / 目标进度 五个维度评分与建议。"""
    return await xtools.tool_get_health_check({})


# ---------------------------------------------------------------------------
# 行情 / 自选工具
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_symbol(query: str) -> str:
    """搜索 A股/基金/指数（按代码或名称，如「茅台」「600519」）。"""
    return await xtools.tool_search_symbol({"query": query})


@mcp.tool()
async def get_quote(symbol: str) -> str:
    """查询单只标的实时行情：现价、涨跌幅、来源（东财/新浪）。symbol 为 6 位代码如 600519。"""
    return await xtools.tool_get_quote({"symbol": symbol})


@mcp.tool()
async def get_kline(symbol: str, period: str = "daily", limit: int = 60) -> str:
    """查询某标的的 K 线走势。symbol=6 位代码，period=daily/weekly/monthly，limit=返回点数（10-500）。"""
    return await xtools.tool_get_kline({"symbol": symbol, "period": period, "limit": limit})


@mcp.tool()
async def add_to_watchlist(symbol: str, name: str = "", kind: str = "股票") -> str:
    """把标的加入自选。name 省略时自动从实时行情获取名称。"""
    return await xtools.tool_add_watchlist({"symbol": symbol, "name": name, "kind": kind})


@mcp.tool()
async def remove_from_watchlist(symbol: str) -> str:
    """自选列表移除标的。"""
    return await xtools.tool_remove_watchlist({"symbol": symbol})


@mcp.tool()
async def get_watchlist() -> str:
    """查询自选列表及其实时行情。"""
    return await xtools.tool_get_watchlist({})


# ---------------------------------------------------------------------------
# 记账 / 记忆工具
# ---------------------------------------------------------------------------


@mcp.tool()
async def record_transaction(text: str) -> str:
    """一句话记账：把用户的记账指令（如「昨天打车 32」「工资 8000 已到账」）解析并写入账本。"""
    return await xtools.tool_record_transaction({"text": text})


@mcp.tool()
async def record_position(symbol: str, shares: float, cost: float, last: float = 0,
                          name: str = "", kind: str = "股票", industry: str = "其他",
                          buy_date: str = "") -> str:
    """记录一笔买入持仓。symbol=代码(6位), shares=份额, cost=成本价, last=现价(自动获取可省略)。"""
    return await xtools.tool_record_position({
        "symbol": symbol, "shares": shares, "cost": cost, "last": last,
        "name": name, "kind": kind, "industry": industry, "buy_date": buy_date,
    })


@mcp.tool()
async def sell_position(symbol: str, shares: float = 0) -> str:
    """卖出/减仓持仓。symbol=代码, shares=份额(省略=全部清仓)。"""
    return await xtools.tool_sell_position({"symbol": symbol, "shares": shares})


@mcp.tool()
async def save_user_memory(content: str) -> str:
    """记住一条用户的长期信息（如「明年计划买房」「每月收入 2 万」）。"""
    return await xtools.tool_save_user_memory({"content": content})


@mcp.tool()
async def get_user_memory(query: str = "", kind: str = "") -> str:
    """查询用户长期记忆。query 关键词检索，kind 类型过滤(fact/preference/goal_related)。"""
    return await xtools.tool_get_user_memory({"query": query, "kind": kind})


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_now() -> str:
    """返回当前日期与时间（服务器本地时区）。"""
    return await xtools.tool_get_now({})


@mcp.tool()
async def web_search(q: str) -> str:
    """联网搜索（免 key，Bing 接口，国内可达）。q 为搜索关键词。"""
    return await xtools.tool_web_search({"q": q})


# ---------------------------------------------------------------------------
# 写操作（需谨慎）：晨报 / 备份
# ---------------------------------------------------------------------------


@mcp.tool()
async def trigger_morning_report(lang: str = "zh") -> str:
    """立即生成今日晨报（组合+账本+财务目标体检）。lang=zh/en。"""
    return await xtools.tool_trigger_morning_report({}, lang=lang)


@mcp.tool()
async def backup_now(lang: str = "zh") -> str:
    """生成本地加密备份包（口令只显示一次，不落盘）。"""
    return await xtools.tool_backup_now({}, lang=lang)


# ---------------------------------------------------------------------------
# 资源暴露（MCP resource）：系统说明
# ---------------------------------------------------------------------------


@mcp.resource("xiaoman://system-prompt")
def system_prompt_resource() -> str:
    """小满系统提示词：描述工具集和 Agent 行为规则。"""
    return (
        "你是小满(xiaoman)财务 Agent，通过 MCP 工具访问用户的本地财务数据。\n"
        "规则：\n"
        "1. 需要数字时必须调用工具获取，绝不编造\n"
        "2. 先给一句话结论，再列关键数字，最后风险项\n"
        "3. 不给具体买卖指令\n"
        "4. 工具失败时如实说明\n"
        "5. 涉及用户背景先查 get_user_memory"
    )


# ---------------------------------------------------------------------------
# 财务数据查询工具（增强）
# ---------------------------------------------------------------------------


async def _compute_net_worth() -> str:
    """计算用户当前净值（确定性的，不依赖 LLM）。"""
    from .calculations.net_worth import calculate_net_worth

    positions = await db.list_positions()
    debts = await db.list_debts()
    snap = calculate_net_worth(positions=positions, debts=debts)
    return json.dumps({
        "date": str(snap.date),
        "total_assets": snap.total_assets,
        "total_liabilities": snap.total_liabilities,
        "net_worth": snap.net_worth,
        "asset_breakdown": snap.asset_breakdown,
        "liability_breakdown": snap.liability_breakdown,
    }, ensure_ascii=False)


async def _compute_financial_health() -> str:
    """计算财务健康评分（五维度 0-100）。"""
    from .calculations.health import HealthInputs, calculate_health_score

    # 从 DB 拿数据
    positions = await db.list_positions()
    txs = await db.list_transactions()
    debts = await db.list_debts()
    settings = await db.get_settings()

    # 计算月度收入 / 支出
    monthly_income = 0.0
    monthly_expense = 0.0
    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    for t in txs:
        if t.get("date", "").startswith(month_prefix):
            amt = float(t.get("amount", 0))
            if amt > 0:
                monthly_income += amt
            else:
                monthly_expense += abs(amt)

    # 月度负债还款
    monthly_debt = sum(float(d.get("monthly", 0) or 0) for d in debts)

    # 现金
    cash = sum(
        float(p.get("last", 0)) * float(p.get("shares", 0))
        for p in positions if p.get("kind") == "现金"
    )

    inputs = HealthInputs(
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        monthly_debt_payment=monthly_debt,
        cash_balance=cash,
        essential_monthly_expense=monthly_expense or 1.0,
        emergency_target_months=float(settings.get("emergency_target_months", 6) or 6),
        positions=[{"name": p.get("name", ""), "kind": p.get("kind", ""),
                     "market_value": float(p.get("last", 0)) * float(p.get("shares", 0))}
                    for p in positions],
    )
    score = calculate_health_score(inputs)
    return json.dumps({
        "score": score.score,
        "grade": score.grade,
        "breakdown": score.breakdown,
    }, ensure_ascii=False)


async def _compute_returns(months: int = 6) -> str:
    """计算收益率（简单收益率从持仓现值 vs 成本）。"""
    from .calculations.returns import calculate_simple_return

    positions = await db.list_positions()

    # 非现金持仓总成本 / 总市值
    total_cost = 0.0
    total_value = 0.0
    for p in positions:
        if p.get("kind") == "现金":
            continue
        shares = float(p.get("shares", 0))
        cost = float(p.get("cost", 0))
        last = float(p.get("last", 0))
        total_cost += shares * cost
        total_value += shares * last

    pnl = total_value - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0

    # 简单收益率：用历史流水做粗略估算
    simple_return = 0.0
    if total_cost > 0:
        try:
            simple_return = calculate_simple_return(total_cost, total_value)
        except ValueError:
            simple_return = 0.0

    return json.dumps({
        "months": months,
        "total_cost": round(total_cost, 2),
        "total_market_value": round(total_value, 2),
        "unrealized_pnl": round(pnl, 2),
        "unrealized_pnl_pct": round(pnl_pct, 2),
        "simple_return": round(simple_return, 6),
    }, ensure_ascii=False)


async def _compute_goal_progress() -> str:
    """查询所有财务目标的进度（on_track/逾期/完成）。"""
    from .calculations.goals import calculate_goal_progress

    goals = await db.list_goals()
    positions = await db.list_positions()
    txs = await db.list_transactions()
    progress = calculate_goal_progress(goals, positions, txs)
    return json.dumps([{
        "name": g.name,
        "target": g.target_amount,
        "current": g.current_amount,
        "progress_pct": g.progress_pct,
        "on_track": g.on_track,
        "months_remaining": g.months_remaining,
        "required_monthly": g.required_monthly,
    } for g in progress], ensure_ascii=False)


async def _import_transactions(source: str, csv_text: str) -> str:
    """批量导入交易：解析 CSV + 去重 + 写入 + 审计。"""
    from ..csvimport import classify as _auto_classify
    from .import_parsers import get_parser

    parser = get_parser(source)
    result = parser.parse(csv_text)

    # 自动分类
    for t in result.transactions:
        if t.category in ("", "其他", "未分类"):
            t.category = _auto_classify(t.item) or "其他"

    # 去重
    existing = await db.list_transactions()
    existing_keys = {(r["date"], round(r["amount"], 2), r["item"]) for r in existing}
    unique_txs = []
    for t in result.transactions:
        key = (t.date, round(t.amount, 2), t.item)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        unique_txs.append(t)

    # 写入
    imported = 0
    for t in unique_txs:
        await db.add_transaction(t.date, t.item, t.category, t.amount)
        imported += 1

    # 审计
    await record_provenance(
        action="import_transactions",
        entity_type="transaction",
        entity_id=f"batch:mcp:{imported}",
        before=None,
        after={"imported": imported, "source": source, "total_in_csv": len(result.transactions)},
        source="mcp",
        username="system",
    )

    return json.dumps({
        "imported": imported,
        "skipped": len(result.transactions) - imported,
        "errors": result.errors,
    }, ensure_ascii=False)


@mcp.tool()
async def get_net_worth() -> str:
    """查询用户当前净值（总资产 - 总负债）。返回资产/负债明细。"""
    return await _compute_net_worth()


@mcp.tool()
async def get_financial_health() -> str:
    """查询财务健康评分（0-100）及五维度拆解（储蓄率/DTI/应急金/集中度/投资多样性）。"""
    return await _compute_financial_health()


@mcp.tool()
async def get_returns(months: int = 6) -> str:
    """查询收益率数据：总成本、总市值、未实现盈亏、简单收益率。months 参数预留用于未来 XIRR 区间计算。"""
    return await _compute_returns(months)


@mcp.tool()
async def get_goal_progress() -> str:
    """查询所有财务目标进度：目标金额、已存金额、进度百分比、是否达标、所需月存。"""
    return await _compute_goal_progress()


@mcp.tool()
async def import_transactions(source: str, csv_text: str) -> str:
    """批量导入交易记录（source: generic/wechat/alipay，csv_text: CSV 文本内容）。自动去重、分类并记录审计日志。"""
    return await _import_transactions(source, csv_text)


@mcp.tool()
async def get_family_summary() -> str:
    """查询家庭整体汇总（总收入/总支出/各成员占比/未结清借贷）"""
    try:
        summary = await db.family_summary()
        return json.dumps(summary, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@mcp.tool()
async def get_provenance(entity_type: str = "", entity_id: str = "", limit: int = 20) -> str:
    """查询操作审计日志（按实体类型/ID 过滤）。返回最近的操作记录（时间/动作/来源/前后快照）。"""
    from .provenance import get_provenances as _get_prov
    rows = await _get_prov(
        entity_type=entity_type or None,
        entity_id=entity_id or None,
        limit=min(limit, 200),
    )
    return json.dumps({"count": len(rows), "provenances": rows}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 集成入口：挂载到 FastAPI 应用
# ---------------------------------------------------------------------------


def mount_to_app(app: Any) -> None:
    """把 MCP Server 挂载到 FastAPI app 的 /mcp 路径（SSE transport）。"""
    if not MCP_AVAILABLE:
        log.info("mcp.skipped: fastmcp unavailable, not mounting")
        return

    import os
    import secrets

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    # FastMCP 提供 ASGI app（SSE transport）
    mcp_asgi = mcp.sse_app()

    # /mcp 走 app.mount 会绕过主 app 的 @app.middleware("http") 中间件链，
    # 如果不用独立鉴权包裹，任何能访问 /mcp 的人都可触发全量财务工具（sell_position/backup_now）。
    class _McpAuthGuard(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            key = os.getenv("API_TOKEN", "").strip()
            if key:
                token = request.query_params.get("token", "")
                header = request.headers.get("authorization", "")
                if not (
                    secrets.compare_digest(token, key)
                    or secrets.compare_digest(header, f"Bearer {key}")
                ):
                    return JSONResponse({"error": "需要访问口令"}, status_code=401)
            # 无口令模式：沿用主 app 同口径 Host 白名单
            return await call_next(request)

    wrapped = _McpAuthGuard(mcp_asgi)
    app.mount("/mcp", wrapped)


async def startup() -> None:
    """MCP Server 启动时检查 DB 可用性。"""
    try:
        await db.fetch_all("SELECT 1")
    except Exception:
        pass  # DB 未就绪时 MCP 工具会在调用时返回错误


if __name__ == "__main__":
    """独立运行 MCP Server（stdio transport，供 Claude Desktop 等接入）。"""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "stdio":
        asyncio.run(mcp.run_async(transport="stdio"))
    else:
        asyncio.run(mcp.run_async(transport="streamable-http", host="0.0.0.0", port=8765))
