"""净值追踪单测：calculate_net_worth / NetWorthSnapshot。"""

from __future__ import annotations

from datetime import date

import pytest

from app.calculations.net_worth import NetWorthSnapshot, calculate_net_worth


class TestNetWorthSnapshot:
    """NetWorthSnapshot dataclass 基础行为测试。"""

    def test_basic_construction(self):
        snap = NetWorthSnapshot(
            date=date(2026, 1, 15),
            total_assets=100000.0,
            total_liabilities=20000.0,
            net_worth=80000.0,
        )
        assert snap.date == date(2026, 1, 15)
        assert snap.total_assets == 100000.0
        assert snap.total_liabilities == 20000.0
        assert snap.net_worth == 80000.0

    def test_default_breakdowns_are_empty(self):
        snap = NetWorthSnapshot(
            date=date.today(),
            total_assets=50000.0,
            total_liabilities=0.0,
            net_worth=50000.0,
        )
        assert snap.asset_breakdown == {}
        assert snap.liability_breakdown == {}


class TestCalculateNetWorth:
    """calculate_net_worth 核心计算逻辑测试。"""

    def test_basic_portfolio(self):
        """股票 + 现金 - 贷款 = 净值。"""
        positions = [
            {"symbol": "600519", "name": "贵州茅台", "kind": "股票", "shares": 100, "last": 1521.0},
            {"symbol": "CASH", "name": "活期现金", "kind": "现金", "shares": 1, "last": 40000.0},
        ]
        debts = [{"name": "房贷", "balance": 500000.0, "rate": 0.045, "monthly": 3500.0}]

        snap = calculate_net_worth(positions, debts=debts)

        # 资产: 100*1521 + 40000 = 192100
        assert snap.total_assets == 192100.0
        # 负债: 500000
        assert snap.total_liabilities == 500000.0
        # 净值: -307900
        assert snap.net_worth == -307900.0

    def test_no_debts(self):
        """无负债场景。"""
        positions = [
            {"symbol": "ABC", "name": "Test Stock", "kind": "股票", "shares": 10, "last": 100.0},
        ]
        snap = calculate_net_worth(positions)
        assert snap.total_assets == 1000.0
        assert snap.total_liabilities == 0.0
        assert snap.net_worth == 1000.0

    def test_separate_cash_accounts(self):
        """传入独立 cash 列表时，现金仓位和独立现金账户累加。"""
        positions = [
            {"symbol": "STOCK", "name": "股票A", "kind": "股票", "shares": 50, "last": 200.0},
        ]
        cash = [{"name": "银行卡", "amount": 30000.0}]

        snap = calculate_net_worth(positions, cash=cash)
        # 10000 + 30000 = 40000
        assert snap.total_assets == 40000.0
        assert snap.net_worth == 40000.0

    def test_negative_shares_raises(self):
        """负数 shares 必须 raise ValueError。"""
        positions = [
            {"symbol": "X", "name": "Bad Stock", "kind": "股票", "shares": -10, "last": 100.0},
        ]
        with pytest.raises(ValueError, match="份额不能为负"):
            calculate_net_worth(positions)

    def test_negative_price_raises(self):
        """负价格必须 raise ValueError。"""
        positions = [
            {"symbol": "X", "name": "Bad Price", "kind": "股票", "shares": 10, "last": -100.0},
        ]
        with pytest.raises(ValueError, match="价格不能为负"):
            calculate_net_worth(positions)

    def test_negative_cash_raises(self):
        """现金余额为负 raise ValueError。"""
        cash = [{"name": "透支账户", "amount": -500.0}]
        with pytest.raises(ValueError, match="现金余额不能为负"):
            calculate_net_worth([], cash=cash)

    def test_debt_with_interest_accrued(self):
        """负债本金 + 应计利息都计入总负债。"""
        positions = [
            {"symbol": "ALLCASH", "name": "全部现金", "kind": "现金", "shares": 1, "last": 100000.0},
        ]
        debts = [
            {"name": "信用卡", "balance": 5000.0, "interest_accrued": 150.0, "monthly": 500.0},
        ]
        snap = calculate_net_worth(positions, debts=debts)
        assert snap.total_liabilities == 5150.0
        assert snap.net_worth == 94850.0

    def test_asset_breakdown_content(self):
        """资产明细正确汇总。"""
        positions = [
            {"symbol": "A", "name": "股票A", "kind": "股票", "shares": 10, "last": 100.0},
            {"symbol": "B", "name": "基金B", "kind": "基金", "shares": 20, "last": 50.0},
        ]
        snap = calculate_net_worth(positions)
        assert snap.asset_breakdown == {"股票A": 1000.0, "基金B": 1000.0}

    def test_as_of_date_custom(self):
        """自定义快照日期。"""
        custom_date = date(2025, 6, 15)
        snap = calculate_net_worth([], as_of=custom_date)
        assert snap.date == custom_date

    def test_rounding_to_two_decimals(self):
        """金额统一 round 到 2 位小数。"""
        positions = [
            {"symbol": "P", "name": "零碎持仓", "kind": "股票", "shares": 3, "last": 33.333},
        ]
        snap = calculate_net_worth(positions)
        assert snap.total_assets == 100.0  # 3 * 33.333 = 99.999 → round = 100.0

    def test_empty_inputs(self):
        """空输入：净值 = 0。"""
        snap = calculate_net_worth([])
        assert snap.total_assets == 0.0
        assert snap.total_liabilities == 0.0
        assert snap.net_worth == 0.0
