"""账单 CSV 解析单测：收支方向、日期校验、缺列兜底。"""

from __future__ import annotations

from app import csvimport


def _run(csv_text: str, year_fill: str = "2026-09") -> tuple[list[dict], list[str]]:
    parsed = csvimport.parse_csv(csv_text)
    mapping = csvimport.detect_mapping(parsed["columns"])
    assert mapping["date"] >= 0 and mapping["amount"] >= 0, mapping
    return csvimport.build_rows(
        mapping, parsed["columns"], parsed["rows"], year_fill=year_fill
    )


def test_unknown_type_skipped_not_income() -> None:
    """类型列取值无法识别（微信「/」、支付宝「不计收支」）时不得判为收入。"""
    csv_text = (
        "交易时间,收/支,交易对方,金额\n"
        "2026-09-10 12:00:00,/,零钱提现,100.00\n"
        "2026-09-11 12:00:00,不计收支,余额宝转入,200.00\n"
        "2026-09-12 12:00:00,支出,滴滴出行,32.00\n"
    )
    rows, skips = _run(csv_text)
    assert [r["amount"] for r in rows] == [-32.0]
    assert sum("收支类型未识别" in s for s in skips) == 2


def test_uppercase_debit_is_expense() -> None:
    csv_text = "交易日期,交易类型,摘要,金额\n2026-09-10,DEBIT,ATM 取款,500.00\n"
    rows, _ = _run(csv_text)
    assert rows[0]["amount"] == -500.0


def test_no_type_column_uses_amount_sign() -> None:
    """没有类型列时按金额正负判定方向（银行流水常见形态）。"""
    csv_text = "交易日期,摘要,金额\n2026-09-10,工资,8000.00\n2026-09-11,房租,-3000.00\n"
    rows, _ = _run(csv_text)
    assert [r["amount"] for r in rows] == [8000.0, -3000.0]


def test_invalid_calendar_date_skipped() -> None:
    """2026-13-45 之类日历非法日期不得入库（否则永远进不了月度聚合）。"""
    csv_text = "交易日期,收/支,交易对方,金额\n2026-13-45,支出,某某,10.00\n"
    rows, skips = _run(csv_text)
    assert rows == []
    assert any("日期" in s for s in skips)


def test_missing_year_without_fill_skipped() -> None:
    csv_text = "交易日期,收/支,交易对方,金额\n09-12,支出,某某,10.00\n"
    rows, skips = _run(csv_text, year_fill="")
    assert rows == []
    assert skips


def test_month_day_only_uses_year_fill() -> None:
    csv_text = "交易日期,收/支,交易对方,金额\n09-12,支出,某某,10.00\n"
    rows, _ = _run(csv_text, year_fill="2026-09")
    assert rows[0]["date"] == "2026-09-12"
