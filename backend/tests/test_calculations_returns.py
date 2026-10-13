"""收益率计算单测：XIRR / TWR / 简单收益率。"""

from __future__ import annotations

from datetime import date

import pytest

from app.calculations.returns import (
    calculate_simple_return,
    calculate_twr,
    calculate_xirr,
    _to_date,
)


class TestCalculateXIRR:
    """XIRR 牛顿迭代法测试。"""

    def test_simple_case(self):
        """已知 XIRR ≈ 8% 的标准案例。"""
        # 2024-01-01 投入 10000，2025-01-01 取回 10800 → IRR = 8%
        cashflows = [
            (date(2024, 1, 1), -10000.0),
            (date(2025, 1, 1), 10800.0),
        ]
        result = calculate_xirr(cashflows)
        assert abs(result - 0.08) < 0.001  # 允许 0.1% 误差

    def test_multiple_cashflows(self):
        """多笔现金流：定投 + 中途取出 + 期末估值。"""
        cashflows = [
            (date(2024, 1, 1), -5000.0),
            (date(2024, 7, 1), -5000.0),
            (date(2025, 1, 1), -5000.0),
            (date(2025, 7, 1), 17000.0),
        ]
        result = calculate_xirr(cashflows)
        # 总投入 15000，终值 17000，约 1.5 年，IRR 约 8-10%
        assert 0.05 < result < 0.15

    def test_two_flows_minimum(self):
        """恰好 2 条现金流（最低要求）。"""
        cashflows = [
            (date(2024, 1, 1), -1000.0),
            (date(2024, 7, 1), 1050.0),
        ]
        result = calculate_xirr(cashflows)
        # 半年 5% → 年化约 10%
        assert result > 0

    def test_insufficient_flows_raises(self):
        """少于 2 条现金流 raise ValueError。"""
        with pytest.raises(ValueError, match="至少需要 2 条"):
            calculate_xirr([(date.today(), 100.0)])

    def test_all_positive_raises(self):
        """全部流入 raise ValueError。"""
        cashflows = [
            (date(2024, 1, 1), 100.0),
            (date(2024, 6, 1), 200.0),
        ]
        with pytest.raises(ValueError, match="同时包含"):
            calculate_xirr(cashflows)

    def test_all_negative_raises(self):
        """全部流出 raise ValueError。"""
        cashflows = [
            (date(2024, 1, 1), -100.0),
            (date(2024, 6, 1), -200.0),
        ]
        with pytest.raises(ValueError, match="同时包含"):
            calculate_xirr(cashflows)

    def test_invalid_date_type_raises(self):
        """日期非 date 类型 raise ValueError。"""
        with pytest.raises(ValueError, match="datetime.date"):
            calculate_xirr([("2024-01-01", -100.0), (date(2024, 6, 1), 110.0)])

    def test_negative_rate_possible(self):
        """亏损场景 XIRR 为负值。"""
        cashflows = [
            (date(2024, 1, 1), -10000.0),
            (date(2025, 1, 1), 9000.0),
        ]
        result = calculate_xirr(cashflows)
        assert result < 0  # 亏损，IRR 为负

    def test_long_time_horizon(self):
        """长期限 XIRR 仍能收敛。"""
        cashflows = [
            (date(2020, 1, 1), -10000.0),
            (date(2025, 1, 1), 16105.1),  # 10% 年化
        ]
        result = calculate_xirr(cashflows)
        assert abs(result - 0.10) < 0.002


class TestCalculateTWR:
    """时间加权收益率测试。"""

    def test_two_valuations_no_flow(self):
        """两个估值点，无外部现金流 = 简单收益率。"""
        txns = [
            {"date": "2024-01-01", "type": "valuation", "amount": 10000.0},
            {"date": "2024-07-01", "type": "valuation", "amount": 11000.0},
        ]
        result = calculate_twr(txns)
        assert abs(result - 0.10) < 0.001

    def test_two_valuations_with_deposit(self):
        """中途追加投入：TWR 应剔除现金流影响。"""
        txns = [
            {"date": "2024-01-01", "type": "valuation", "amount": 10000.0},
            {"date": "2024-04-01", "type": "deposit", "amount": 5000.0},
            {"date": "2024-07-01", "type": "valuation", "amount": 16500.0},
        ]
        # 第一段：10000 → 10000 + 5000 = 15000, r1 = 0
        # 第二段：15000 → 16500, r2 = 0.10
        # TWR = (1 + 0) * (1 + 0.10) - 1 = 0.10
        result = calculate_twr(txns)
        assert abs(result - 0.10) < 0.001

    def test_multiple_subperiods(self):
        """多期几何连乘。"""
        txns = [
            {"date": "2024-01-01", "type": "valuation", "amount": 10000.0},
            {"date": "2024-04-01", "type": "valuation", "amount": 10500.0},
            {"date": "2024-07-01", "type": "valuation", "amount": 11000.0},
            {"date": "2024-10-01", "type": "valuation", "amount": 10800.0},
        ]
        result = calculate_twr(txns)
        # (1.05) * (1.0476) * (0.9818) - 1 ≈ 7.88%
        assert 0.05 < result < 0.12

    def test_insufficient_records_raises(self):
        """少于 2 条记录 raise ValueError。"""
        with pytest.raises(ValueError, match="至少需要 2 条"):
            calculate_twr([{"date": "2024-01-01", "type": "valuation", "amount": 1000.0}])

    def test_insufficient_valuations_raises(self):
        """少于 2 个估值点 raise ValueError。"""
        txns = [
            {"date": "2024-01-01", "type": "deposit", "amount": 1000.0},
            {"date": "2024-06-01", "type": "withdraw", "amount": 500.0},
        ]
        with pytest.raises(ValueError, match="至少需要 2 个估值点"):
            calculate_twr(txns)

    def test_negative_valuation_raises(self):
        """负估值 raise ValueError。"""
        txns = [
            {"date": "2024-01-01", "type": "valuation", "amount": -1000.0},
            {"date": "2024-06-01", "type": "valuation", "amount": 1000.0},
        ]
        with pytest.raises(ValueError, match="估值金额必须为正"):
            calculate_twr(txns)

    def test_withdraw_flow(self):
        """取出现金流正确处理。"""
        txns = [
            {"date": "2024-01-01", "type": "valuation", "amount": 10000.0},
            {"date": "2024-04-01", "type": "withdraw", "amount": 2000.0},
            {"date": "2024-07-01", "type": "valuation", "amount": 9000.0},
        ]
        # 第二段：期初 10000 - 取出 2000 = 8000，期末 9000
        # r2 = 9000 / (10000 - 2000) - 1 = 9000/8000 - 1 = 0.125
        result = calculate_twr(txns)
        assert abs(result - 0.125) < 0.001


class TestCalculateSimpleReturn:
    """简单收益率测试。"""

    def test_basic_gain(self):
        """基础盈利。"""
        result = calculate_simple_return(10000.0, 11000.0)
        assert abs(result - 0.10) < 0.0001

    def test_basic_loss(self):
        """亏损场景。"""
        result = calculate_simple_return(10000.0, 9000.0)
        assert abs(result - (-0.10)) < 0.0001

    def test_with_net_inflows(self):
        """期间追加投入。"""
        # 期初 10000，期间投入 5000，期末 17000
        # r = (17000 - 10000 - 5000) / (10000 + 5000) = 2000/15000 = 0.1333
        result = calculate_simple_return(10000.0, 17000.0, 5000.0)
        assert abs(result - 0.133333) < 0.001

    def test_zero_inflows(self):
        """零净流入 = 基础收益率。"""
        result = calculate_simple_return(5000.0, 5500.0, 0.0)
        assert abs(result - 0.10) < 0.0001

    def test_negative_start_value_raises(self):
        """期初价值非正 raise ValueError。"""
        with pytest.raises(ValueError, match="期初价值必须为正"):
            calculate_simple_return(0.0, 1000.0)

    def test_negative_denominator_raises(self):
        """分母为负 raise ValueError。"""
        with pytest.raises(ValueError, match="分母为零或负"):
            calculate_simple_return(1000.0, 500.0, -2000.0)

    def test_large_return(self):
        """大收益率场景。"""
        result = calculate_simple_return(10000.0, 50000.0)
        assert abs(result - 4.0) < 0.0001  # 400%


class TestToDate:
    """日期解析工具函数测试。"""

    def test_date_object_passthrough(self):
        d = date(2024, 3, 15)
        assert _to_date(d) == d

    def test_string_date_parsing(self):
        assert _to_date("2024-03-15") == date(2024, 3, 15)

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            _to_date("not-a-date")
