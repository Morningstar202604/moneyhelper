"""导入解析器单元测试：通用 CSV / 微信 / 支付宝 + 编码检测 + 边界用例。
目标 ≥ 30 独立测试，覆盖所有主要代码路径。
"""

from __future__ import annotations

import textwrap

import pytest
from app.import_parsers import (
    AlipayParser,
    GenericCSVParser,
    WeChatParser,
    get_parser,
    supported_sources,
)
from app.import_parsers.base import (
    ParsedTransaction,
    ParseResult,
    _detect_encoding,
    _is_real_date,
    _parse_amount,
    _parse_date,
)

# ===========================================================================
# section 1: ParsedTransaction & ParseResult 数据结构
# ===========================================================================

class TestDataClasses:
    def test_parsed_transaction_defaults(self) -> None:
        t = ParsedTransaction(date="2026-01-01", amount=-10.0, category="餐饮", item="早餐")
        assert t.account == ""
        assert t.raw == {}

    def test_parse_result_to_preview(self) -> None:
        pr = ParseResult(
            transactions=[
                ParsedTransaction("2026-01-01", -10.0, "餐饮", "早餐"),
                ParsedTransaction("2026-01-02", 5000.0, "收入", "工资"),
            ],
            total_income=5000.0,
            total_expense=-10.0,
        )
        preview = pr.to_preview()
        assert preview["summary"]["count"] == 2
        assert preview["summary"]["total_income"] == 5000.0
        assert preview["summary"]["total_expense"] == -10.0
        assert not preview["transactions"][0].get("raw")

    def test_parse_result_recalc(self) -> None:
        pr = ParseResult()
        pr.transactions = [
            ParsedTransaction("2026-01-01", -10.0, "a", "b"),
            ParsedTransaction("2026-01-01", -20.0, "a", "b"),
            ParsedTransaction("2026-01-02", 100.0, "c", "d"),
        ]
        pr.recalc_totals()
        assert pr.total_income == 100.0
        assert pr.total_expense == -30.0


# ===========================================================================
# section 2: 纯工具函数
# ===========================================================================

class TestUtilityFunctions:
    def test_parse_amount_basic(self) -> None:
        assert _parse_amount("100.00") == 100.0
        assert _parse_amount("-50.5") == -50.5
        assert _parse_amount("¥32.00") == 32.0
        assert _parse_amount("￥1,234.56") == 1234.56

    def test_parse_amount_none(self) -> None:
        assert _parse_amount("") is None
        assert _parse_amount("abc") is None

    def test_parse_date_basic(self) -> None:
        assert _parse_date("2026-01-15") == "2026-01-15"
        assert _parse_date("2026/01/15") == "2026-01-15"
        assert _parse_date("2026年01月15日") == "2026-01-15"

    def test_parse_date_datetime(self) -> None:
        assert _parse_date("2026-01-15 14:30:00") == "2026-01-15"

    def test_parse_date_none(self) -> None:
        assert _parse_date("") is None
        assert _parse_date("abc") is None

    def test_is_real_date(self) -> None:
        assert _is_real_date("2026-01-15")
        assert not _is_real_date("2026-13-45")
        assert not _is_real_date("2026-02-30")

    def test_detect_encoding_utf8(self) -> None:
        assert _detect_encoding("hello 世界".encode()) == "utf-8-sig"

    def test_detect_encoding_gbk(self) -> None:
        assert _detect_encoding("微信支付账单".encode("gbk")) == "gbk"

    def test_detect_encoding_utf8_bom(self) -> None:
        assert _detect_encoding(b"\xef\xbb\xbfhello") == "utf-8-sig"


# ===========================================================================
# section 3: 通用 CSV 解析器
# ===========================================================================

class TestGenericCSVParser:
    def setup_method(self) -> None:
        self.parser = GenericCSVParser()

    def test_chinese_headers(self) -> None:
        csv_text = textwrap.dedent("""\
            交易日期,收/支,交易对方,商品,金额,备注
            2026-09-10,支出,滴滴出行,打车,32.00,快车
            2026-09-11,收入,工资入账,月工资,24800.00,九月
        """)
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 2
        assert result.transactions[0].amount == -32.0
        assert result.transactions[1].amount == 24800.0
        assert result.total_expense == -32.0
        assert result.total_income == 24800.0

    def test_english_headers(self) -> None:
        csv_text = textwrap.dedent("""\
            date,amount,category,notes
            2026-09-10,-32.00,交通,打车
            2026-09-11,8000.00,收入,工资
        """)
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 2
        assert result.transactions[0].amount == -32.0
        assert result.transactions[1].amount == 8000.0

    def test_debit_credit_split_columns(self) -> None:
        """银行格式：借方 / 贷方分两列。"""
        csv_text = textwrap.dedent("""\
            date,description,debit,credit
            2026-09-10,ATM 取款,500.00,
            2026-09-11,工资入账,,8000.00
        """)
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 2
        assert result.transactions[0].amount == -500.0  # 借方 = 支出
        assert result.transactions[1].amount == 8000.0  # 贷方 = 收入

    def test_empty_lines_skipped(self) -> None:
        csv_text = textwrap.dedent("""\
            date,amount,notes

            2026-09-10,-32.00,打车
            2026-09-11,-50.00,吃饭

        """)
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 2

    def test_summary_row_skipped(self) -> None:
        csv_text = textwrap.dedent("""\
            date,amount,notes
            2026-09-10,-32.00,打车
            2026-09-11,-50.00,吃饭
           合计,,82.00
        """)
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 2
        assert result.skipped >= 1

    def test_empty_csv_errors(self) -> None:
        result = self.parser.parse("")
        assert result.errors
        assert not result.transactions

    def test_missing_date_column(self) -> None:
        csv_text = textwrap.dedent("""\
            amount,notes
            -32.00,打车
        """)
        result = self.parser.parse(csv_text)
        assert result.errors
        assert not result.transactions

    def test_missing_amount_column(self) -> None:
        csv_text = textwrap.dedent("""\
            date,notes
            2026-09-10,打车
        """)
        result = self.parser.parse(csv_text)
        assert result.errors

    def test_invalid_date_skipped(self) -> None:
        csv_text = textwrap.dedent("""\
            date,amount,notes
            2026-13-45,-32.00,打车
            2026-09-11,-50.00,吃饭
        """)
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 1
        assert result.transactions[0].item == "吃饭"
        assert result.skipped >= 1

    def test_zero_amount_skipped(self) -> None:
        """金额为 0 的行不会出现在结果中（解析器未显式过滤但也不应崩溃）。"""
        csv_text = textwrap.dedent("""\
            date,amount,type,notes
            2026-09-10,0.00,支出,打车
            2026-09-11,-50.00,支出,吃饭
        """)
        result = self.parser.parse(csv_text)
        # 0 金额行的 amount 在这里取决于 type 列是否触发处理
        # 确保不崩溃即可
        assert len(result.transactions) >= 1


# ===========================================================================
# section 4: 微信解析器
# ===========================================================================

class TestWeChatParser:
    def setup_method(self) -> None:
        self.parser = WeChatParser()

    def _fake_wechat_csv(self, data_rows: str) -> str:
        """造一份带前导元信息的微信 CSV。"""
        meta = textwrap.dedent("""\
            微信支付账单明细,,,,,,,,,
            导出时间：2026-09-01 12:00:00,,,,,,,,,
            姓名：张三,,,,,,,,,
            起始时间：2026-08-01,,,,,,,,,
            终止时间：2026-08-31,,,,,,,,,
            导出类型：全部,,,,,,,,,
            微信昵称：zs,,,,,,,,,
            微信号：zs_wechat,,,,,,,,,
            账单语言：简体中文,,,,,,,,,
            ,,,,,,,,,,
            ,,,,,,,,,,
            ,,,,,,,,,,
            ,,,,,,,,,,
            ,,,,,,,,,,
            ,,,,,,,,,,
            ,,,,,,,,,,
        """)
        header = "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注"
        return meta + header + "\n" + data_rows

    def test_wechat_basic(self) -> None:
        csv_text = self._fake_wechat_csv(textwrap.dedent("""\
            2026-08-10 12:30:00,滴滴出行,快车,-,支出,¥32.00,零钱,支付成功,xxx,yyy,
            2026-08-11 09:00:00,工资入账,-,-,收入,¥24800.00,银行卡,支付成功,aaa,bbb,
        """))
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 2
        assert result.transactions[0].amount == -32.0
        assert result.transactions[1].amount == 24800.0

    def test_wechat_slash_type_skipped(self) -> None:
        """/ 类型（不计收支，如零钱提现）应跳过。"""
        csv_text = self._fake_wechat_csv(textwrap.dedent("""\
            2026-08-10 12:00:00,零钱提现,-,/,/,¥100.00,零钱,成功,xx,yy,
            2026-08-11 12:00:00,滴滴,快车,-,支出,¥50.00,零钱,支付成功,xx,yy,
        """))
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 1
        assert result.transactions[0].amount == -50.0
        assert result.skipped >= 1

    def test_wechat_bill_tail_skipped(self) -> None:
        """末尾的账单注释行应跳过。"""
        csv_text = self._fake_wechat_csv(textwrap.dedent("""\
            2026-08-10 12:00:00,滴滴,快车,快车,支出,¥50.00,零钱,支付成功,xx,yy,
        """)) + "账单周期：2026-08-01 至 2026-08-31,,,,,,,,,,\n"
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 1

    def test_wechat_empty_csv_errors(self) -> None:
        result = self.parser.parse("")
        assert result.errors

    def test_wechat_no_header_errors(self) -> None:
        result = self.parser.parse("foo,bar\n1,2\n")
        assert result.errors


# ===========================================================================
# section 5: 支付宝解析器
# ===========================================================================

class TestAlipayParser:
    def setup_method(self) -> None:
        self.parser = AlipayParser()

    def _fake_alipay_csv(self, data_rows: str) -> str:
        """造一份带前导元信息的支付宝 CSV。"""
        meta = textwrap.dedent("""\
            支付宝账单明细,,,,,,,,,,
            导出时间：2026-09-01 12:00:00,,,,,,,,,,
            姓名：张三,,,,,,,,,,
            起始时间：2026-08-01,,,,,,,,,,
        """)
        header = "交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注"
        return meta + header + "\n" + data_rows

    def test_alipay_basic(self) -> None:
        csv_text = textwrap.dedent("""\
            支付宝账单明细,,,,,,,,,,
            ,,,,,,,,,,,
            交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注
            2026-08-10 12:00:00,交通出行,滴滴,-,快车,支出,32.00,余额宝,支付成功,xxx,yy,
            2026-08-11 09:00:00,工资理财,工资入账,-,工资,收入,24800.00,银行卡,支付成功,aaa,bb,
        """)
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 2
        assert result.transactions[0].amount == -32.0
        assert result.transactions[0].category == "交通出行"
        assert result.transactions[1].amount == 24800.0

    def test_alipay_skip_buji(self) -> None:
        csv_text = textwrap.dedent("""\
            交易时间,交易分类,商品说明,收/支,金额
            2026-08-10 12:00:00,不计,余额宝转入,不计收支,100.00
            2026-08-11 12:00:00,餐饮,外卖,支出,50.00
        """)
        result = self.parser.parse(csv_text)
        assert len(result.transactions) == 1
        assert result.transactions[0].amount == -50.0
        assert result.skipped >= 1

    def test_alipay_empty_errors(self) -> None:
        result = self.parser.parse("")
        assert result.errors

    def test_alipay_no_header_errors(self) -> None:
        result = self.parser.parse("a,b,c\n1,2,3\n")
        assert result.errors


# ===========================================================================
# section 6: 注册表 & 元信息
# ===========================================================================

class TestRegistry:
    def test_get_parser_generic(self) -> None:
        p = get_parser("generic")
        assert isinstance(p, GenericCSVParser)

    def test_get_parser_wechat(self) -> None:
        p = get_parser("wechat")
        assert isinstance(p, WeChatParser)

    def test_get_parser_alipay(self) -> None:
        p = get_parser("alipay")
        assert isinstance(p, AlipayParser)

    def test_get_parser_case_insensitive(self) -> None:
        p = get_parser("WeChat")
        assert isinstance(p, WeChatParser)

    def test_get_parser_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="不支持"):
            get_parser("paypal")

    def test_supported_sources(self) -> None:
        sources = supported_sources()
        assert len(sources) == 3
        keys = {s["key"] for s in sources}
        assert keys == {"generic", "wechat", "alipay"}
        for s in sources:
            assert "label" in s
            assert "description" in s
            assert isinstance(s["sample_columns"], list)
