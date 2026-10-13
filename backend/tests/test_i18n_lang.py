"""界面语言 i18n：回答与确定性兜底文案跟随 lang（zh/en）。

覆盖：
- analysis：no_data_answer / health_report_text 双语
- service：_try_nl_add 回执 / _run_general 兜底 双语
- 图：run_graph lang 贯穿（AgentState.lang 字段，LangGraph 不会丢弃）
"""

from __future__ import annotations

from typing import Any

from app import analysis, service


async def _collect(run: Any, question: str, thread_id: str | None = None, lang: str = "zh") -> tuple[list[dict], dict]:
    events: list[dict[str, Any]] = []

    async def emit(ev: dict[str, Any]) -> None:
        events.append(ev)

    result = await run(question, emit, thread_id, lang=lang)
    return events, result


# ---------------------------------------------------------------------------
# analysis 模板
# ---------------------------------------------------------------------------


def test_no_data_answer_bilingual() -> None:
    zh = analysis.no_data_answer("zh")
    en = analysis.no_data_answer("en")
    assert "记一笔" in zh and "还没有录入任何数据" in zh
    assert "Record a transaction" in en and "haven't recorded any data" in en


def test_health_report_text_bilingual() -> None:
    report = analysis.health_check(
        {"total_market_value": 100000, "total_pnl": -5000, "concentration": {"asset_breaches": [{"name": "贵州茅台"}]}},
        {"income": 12000, "net": 1000, "savings_rate": 10, "dti_pct": 50, "high_rate_debts": [{"name": "信用卡分期"}], "debt_monthly": 500, "emergency": {"has_data": True, "ok": False, "months_covered": 2, "target_months": 6}},
        [],
    )
    zh = analysis.health_report_text(report, "zh")
    en_report = analysis.health_check(
        {"total_market_value": 100000, "total_pnl": -5000, "concentration": {"asset_breaches": [{"name": "贵州茅台"}]}},
        {"income": 12000, "net": 1000, "savings_rate": 10, "dti_pct": 50, "high_rate_debts": [{"name": "信用卡分期"}], "debt_monthly": 500, "emergency": {"has_data": True, "ok": False, "months_covered": 2, "target_months": 6}},
        [],
        lang="en",
    )
    en = analysis.health_report_text(en_report, "en")
    assert "财务体检综合评分 20 分" in zh and "资产配置（需关注）" in zh
    assert "Financial health score: 20" in en and "Asset mix (Attention)" in en
    assert "Suggestion:" in en and "below the 20.0% target" in en
    assert "concentration breach" in en and "high-interest debt" in en


# ---------------------------------------------------------------------------
# service 确定性兜底
# ---------------------------------------------------------------------------


async def test_run_general_fallback_lang(temp_db, monkeypatch) -> None:
    """通用问题 + lang=en：未接模型时兜底文案为英文。"""
    async def _no_llm() -> bool:
        return False
    monkeypatch.setattr(service.llm, "llm_available", _no_llm)
    _, result = await _collect(service.run_question, "帮我写一段感谢信", lang="en")
    assert "No model is connected" in result["answer"]
    assert result["route"] == "general"


async def test_nl_add_receipt_bilingual(temp_db, monkeypatch) -> None:
    """一句话记账回执跟随 lang（en 时英文回执，仍入账）。"""
    async def _no_llm() -> bool:
        return False
    monkeypatch.setattr(service.llm, "llm_available", _no_llm)
    _, zh = await _collect(service.run_question, "昨天打车 32 元", thread_id="t-zh", lang="zh")
    assert "已记一笔" in zh["answer"]
    _, en = await _collect(service.run_question, "昨天打车 32 元", thread_id="t-en", lang="en")
    assert "Recorded:" in en["answer"] and "CNY" in en["answer"]


# ---------------------------------------------------------------------------
# 图 lang 贯穿（LangGraph state 不丢字段）
# ---------------------------------------------------------------------------


async def test_graph_lang_reaches_finalize(temp_db, monkeypatch) -> None:
    """体检 + lang=en：确定性体检报告为英文壳（回归 AgentState.lang 丢弃缺陷）。"""
    async def _no_llm() -> bool:
        return False
    monkeypatch.setattr(service.llm, "llm_available", _no_llm)
    _, result = await _collect(service.run_question, "帮我体检一下财务状况", lang="en")
    assert "Financial health score" in result["answer"]
    _, zh = await _collect(service.run_question, "帮我体检一下财务状况", lang="zh")
    assert "财务体检综合评分" in zh["answer"]


def test_health_check_dimensions_bilingual() -> None:
    """五维体检结论/建议完整双语：zh 默认不变，en 输出英文 title/detail/suggestion。"""
    market = {
        "total_market_value": 100000,
        "total_pnl": -5000,
        "concentration": {"asset_breaches": [{"name": "贵州茅台"}]},
    }
    ledger = {
            "income": 12000,
            "net": 1000,
            "savings_rate": 10,
            "dti_pct": 50,
            "high_rate_debts": [{"name": "信用卡分期"}],
            "emergency": {"has_data": True, "ok": False, "months_covered": 2, "target_months": 6},
            "debt_monthly": 500,
        }
    zh = analysis.health_check(market, ledger, [])
    en = analysis.health_check(market, ledger, [], lang="en")
    assert zh["dimensions"][0]["title"] == "资产配置"
    assert "集中度超限" in zh["dimensions"][0]["detail"]
    assert "建议：" not in zh["dimensions"][0]["suggestion"]
    en_dims = {d["key"]: d for d in en["dimensions"]}
    assert en_dims["portfolio"]["title"] == "Asset mix"
    assert "concentration breach" in en_dims["portfolio"]["detail"]
    assert en_dims["cashflow"]["title"] == "Cash flow"
    assert "below the 20.0% target" in en_dims["cashflow"]["detail"]
    assert en_dims["debt"]["title"] == "Debt health"
    assert "high-interest debt" in en_dims["debt"]["detail"]
    assert en_dims["emergency"]["title"] == "Emergency fund"
    assert "below the 6-month target" in en_dims["emergency"]["detail"]
    assert en_dims["emergency"]["suggestion"].startswith("Top up the emergency fund")


def test_health_report_en_uses_english_dimensions() -> None:
    """en 报告直接使用 health_check 的英文维度文案（无中文残留）。"""
    report = analysis.health_check(
        {"total_market_value": 100000, "total_pnl": 1000, "concentration": {}},
        {"net": 500, "savings_rate": 25, "dti_pct": 10, "debt_monthly": 0, "emergency": {"has_data": False}},
        [],
        lang="en",
    )
    text = analysis.health_report_text(report, "en")
    assert "Financial health score" in text
    assert "Asset mix (Healthy)" in text
    assert "CNY" in text and "well diversified" in text
