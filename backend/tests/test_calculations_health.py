"""财务健康评分单测：FinancialHealthScore / calculate_health_score。"""

from __future__ import annotations

import pytest

from app.calculations.health import (
    FinancialHealthScore,
    HealthInputs,
    calculate_health_score,
)


class TestFinancialHealthScore:
    """FinancialHealthScore dataclass 测试。"""

    def test_basic_construction(self):
        score = FinancialHealthScore(
            score=75,
            grade="B",
            breakdown={"savings_rate": {"score": 15, "max": 20}},
        )
        assert score.score == 75
        assert score.grade == "B"
        assert score.breakdown["savings_rate"]["score"] == 15


class TestCalculateHealthScore:
    """calculate_health_score 五维评分测试。"""

    def test_perfect_score(self):
        """满分场景：储蓄率 30%、无负债、应急金 12 个月、分散持仓、5 项投资。"""
        inputs = HealthInputs(
            monthly_income=20000.0,
            monthly_expense=14000.0,
            monthly_debt_payment=0.0,
            cash_balance=60000.0,
            essential_monthly_expense=5000.0,
            emergency_target_months=6.0,
            positions=[
                {"name": "股票A", "kind": "股票", "market_value": 10000.0},
                {"name": "股票B", "kind": "股票", "market_value": 8000.0},
                {"name": "基金C", "kind": "基金", "market_value": 7000.0},
                {"name": "债券D", "kind": "债券", "market_value": 5000.0},
                {"name": "黄金E", "kind": "黄金", "market_value": 3000.0},
            ],
        )
        result = calculate_health_score(inputs)
        assert result.score >= 85
        assert result.grade == "A"
        assert result.breakdown["savings_rate"]["score"] == 20
        assert result.breakdown["dti"]["score"] == 20

    def test_zero_score(self):
        """零分场景：负储蓄率、高 DTI、无应急金、集中持仓、无投资。"""
        inputs = HealthInputs(
            monthly_income=5000.0,
            monthly_expense=8000.0,  # 负储蓄率
            monthly_debt_payment=3000.0,  # DTI = 60%
            cash_balance=0.0,
            essential_monthly_expense=5000.0,
            positions=[
                {"name": "超集中持仓", "kind": "股票", "market_value": 100000.0},
            ],
        )
        result = calculate_health_score(inputs)
        assert result.score < 40
        assert result.grade == "D" or result.grade == "F"

    def test_moderate_score(self):
        """中等水平：储蓄率接近建议线、DTI 偏高、应急金不足、持仓集中。"""
        inputs = HealthInputs(
            monthly_income=10000.0,
            monthly_expense=8200.0,  # 储蓄率 18%（低于建议线 20%）
            monthly_debt_payment=2500.0,  # DTI = 25%
            cash_balance=9000.0,  # 应急金仅 3 个月
            essential_monthly_expense=3000.0,
            positions=[
                # 单一持仓 71.4% > 40% → 集中度超限扣分
                {"name": "超集中持仓", "kind": "股票", "market_value": 50000.0},
                {"name": "小持仓", "kind": "基金", "market_value": 20000.0},
            ],
        )
        result = calculate_health_score(inputs)
        # 中等水平应落在 C 或 D 档
        assert 25 <= result.score <= 70
        assert result.grade in ("C", "D")

    def test_no_income_neutral_score(self):
        """无收入数据时使用中性分。"""
        inputs = HealthInputs(
            monthly_income=0.0,
            monthly_expense=0.0,
            monthly_debt_payment=1000.0,
            cash_balance=5000.0,
            essential_monthly_expense=3000.0,
        )
        result = calculate_health_score(inputs)
        # 储蓄率中性分 10，DTI 有负债无收入扣分
        assert result.breakdown["savings_rate"]["score"] == 10

    def test_concentration_breach(self):
        """集中度超限扣分。"""
        inputs = HealthInputs(
            monthly_income=20000.0,
            monthly_expense=10000.0,
            cash_balance=60000.0,
            essential_monthly_expense=5000.0,
            positions=[
                {"name": "超大持仓A", "kind": "股票", "market_value": 90000.0},
                {"name": "小持仓B", "kind": "基金", "market_value": 5000.0},
                {"name": "小持仓C", "kind": "债券", "market_value": 5000.0},
            ],
        )
        result = calculate_health_score(inputs)
        # 超大持仓A = 90% > 40% → 集中度扣分
        assert result.breakdown["concentration_risk"]["score"] < 20

    def test_diversity_score_mapping(self):
        """投资多样性按持仓数量评分。"""
        # 1 项 → 5 分
        inputs_1 = HealthInputs(
            monthly_income=10000.0,
            monthly_expense=5000.0,
            positions=[{"name": "X", "kind": "股票", "market_value": 1000.0}],
        )
        assert calculate_health_score(inputs_1).breakdown["investment_diversity"]["score"] == 5

        # 3 项 → 15 分
        inputs_3 = HealthInputs(
            monthly_income=10000.0,
            monthly_expense=5000.0,
            positions=[
                {"name": "A", "kind": "股票", "market_value": 1000.0},
                {"name": "B", "kind": "基金", "market_value": 1000.0},
                {"name": "C", "kind": "债券", "market_value": 100.0},
            ],
        )
        assert calculate_health_score(inputs_3).breakdown["investment_diversity"]["score"] == 15

    def test_emergency_fund_above_target(self):
        """应急金超过目标值满分。"""
        inputs = HealthInputs(
            monthly_income=10000.0,
            monthly_expense=7000.0,
            cash_balance=60000.0,
            essential_monthly_expense=5000.0,
            emergency_target_months=6.0,
        )
        result = calculate_health_score(inputs)
        assert result.breakdown["emergency_fund_months"]["score"] == 20

    def test_dti_zero_score_max(self):
        """DTI 为 0（无负债）得满分。"""
        inputs = HealthInputs(
            monthly_income=10000.0,
            monthly_expense=8000.0,
            monthly_debt_payment=0.0,
        )
        result = calculate_health_score(inputs)
        # DTI score 应该很高
        assert result.breakdown["dti"]["score"] >= 18

    def test_score_range_0_to_100(self):
        """总分必须在 0-100 范围内。"""
        # 极端：全零输入
        inputs = HealthInputs()
        result = calculate_health_score(inputs)
        assert 0 <= result.score <= 100

    def test_breakdown_has_all_five_dimensions(self):
        """输出必须包含全部五维。"""
        inputs = HealthInputs(monthly_income=10000.0, monthly_expense=8000.0)
        result = calculate_health_score(inputs)
        expected_keys = {"savings_rate", "dti", "emergency_fund_months", "concentration_risk", "investment_diversity"}
        assert set(result.breakdown.keys()) == expected_keys

    def test_grade_mapping(self):
        """等级映射正确。"""
        # A 级需 >= 85
        inputs_a = HealthInputs(
            monthly_income=30000.0, monthly_expense=15000.0,
            cash_balance=90000.0, essential_monthly_expense=5000.0,
            positions=[
                {"name": "A", "kind": "股票", "market_value": 5000.0},
                {"name": "B", "kind": "基金", "market_value": 5000.0},
                {"name": "C", "kind": "债券", "market_value": 5000.0},
                {"name": "D", "kind": "黄金", "market_value": 5000.0},
                {"name": "E", "kind": "REITs", "market_value": 5000.0},
                {"name": "F", "kind": "现金", "market_value": 5000.0},
            ],
        )
        assert calculate_health_score(inputs_a).grade == "A"
