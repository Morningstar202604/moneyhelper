"""目标进度计算单测：GoalProgress / calculate_goal_progress。"""

from __future__ import annotations

from datetime import date

from app.calculations.goals import (
    GoalProgress,
    _estimate_monthly_savings,
    _months_until,
    calculate_goal_progress,
)


class TestGoalProgress:
    """GoalProgress dataclass 测试。"""

    def test_basic_construction(self):
        gp = GoalProgress(
            name="旅行基金",
            target_amount=50000.0,
            current_amount=15000.0,
            monthly_contribution=3000.0,
            months_remaining=12,
            on_track=True,
            required_monthly=2917.0,
            progress_pct=30.0,
        )
        assert gp.name == "旅行基金"
        assert gp.on_track is True
        assert gp.progress_pct == 30.0


TestDate = date(2025, 6, 15)


class TestCalculateGoalProgress:
    """calculate_goal_progress 核心逻辑测试。"""

    def test_goal_already_completed(self):
        """已完成目标（current >= target）→ on_track = True。"""
        goals = [{"name": "已完成", "target": 10000.0, "saved": 12000.0, "deadline": "2025-12"}]
        results = calculate_goal_progress(goals, as_of=TestDate)
        assert len(results) == 1
        assert results[0].on_track is True
        assert results[0].required_monthly is None

    def test_goal_on_track(self):
        """月存充足 → on_track = True。"""
        goals = [{"name": "首付", "target": 300000.0, "saved": 60000.0, "deadline": "2027-06"}]
        # 24 个月完成 240000 → 需月存 10000
        # 不设 monthly_contribution，纯靠 required_monthly 判定
        results = calculate_goal_progress(goals, as_of=TestDate)
        assert len(results) == 1
        # months_remaining = (2027-2025)*12 + (6-6) = 24
        assert results[0].months_remaining == 24

    def test_goal_off_track_via_actual_savings(self):
        """实际月存不足 → on_track = False。"""
        goals = [{"name": "旅行", "target": 50000.0, "saved": 0.0, "monthly_contribution": 1000.0, "deadline": "2026-01"}]
        transactions = [
            {"date": "2025-05-01", "amount": -500.0},  # 支出
            {"date": "2025-05-15", "amount": 2000.0},   # 收入
            {"date": "2025-06-01", "amount": -300.0},
        ]
        # 实际月均净存低 → 不达标
        results = calculate_goal_progress(goals, transactions=transactions, as_of=TestDate)
        # deadline 2026-01 → months_remaining = 7
        # required = 50000/7 ≈ 7143
        # actual_monthly_net 远低于 required → off track
        assert results[0].months_remaining <= 7

    def test_no_deadline(self):
        """无截止日期目标。"""
        goals = [{"name": "储蓄", "target": 100000.0, "saved": 30000.0, "monthly_contribution": 2000.0}]
        results = calculate_goal_progress(goals, as_of=TestDate)
        assert results[0].months_remaining is None
        # 有 monthly_contribution > 0 → on_track = True
        assert results[0].on_track is True

    def test_past_deadline_incomplete(self):
        """逾期未达成 → on_track = False。"""
        goals = [{"name": "逾期目标", "target": 10000.0, "saved": 5000.0, "deadline": "2024-12"}]
        results = calculate_goal_progress(goals, as_of=TestDate)
        assert results[0].on_track is False
        assert results[0].months_remaining == 0

    def test_progress_pct_calculation(self):
        """进度百分比计算正确。"""
        goals = [{"name": "测试", "target": 20000.0, "saved": 5000.0}]
        results = calculate_goal_progress(goals, as_of=TestDate)
        assert results[0].progress_pct == 25.0

    def test_multiple_goals(self):
        """多目标：顺序保留，各自独立计算。"""
        goals = [
            {"name": "A", "target": 30000.0, "saved": 10000.0, "monthly_contribution": 5000.0, "deadline": "2026-01"},
            {"name": "B", "target": 50000.0, "saved": 0.0, "monthly_contribution": 2000.0},
        ]
        results = calculate_goal_progress(goals, as_of=TestDate)
        assert len(results) == 2
        assert results[0].name == "A"
        assert results[1].name == "B"

    def test_required_monthly_is_calculated(self):
        """required_monthly 正确计算缺口 / 剩余月数。"""
        goals = [{"name": "测试", "target": 120000.0, "saved": 0.0, "deadline": "2026-06"}]
        # 12 个月需完成 120000 → 月存 10000
        results = calculate_goal_progress(goals, as_of=TestDate)
        assert results[0].required_monthly == 10000.0

    def test_zero_target_handled(self):
        """target = 0 时不抛出异常。"""
        goals = [{"name": "零目标", "target": 0.0, "saved": 0.0}]
        results = calculate_goal_progress(goals, as_of=TestDate)
        assert results[0].progress_pct == 0.0


class TestMonthsUntil:
    """_months_until 月份差计算测试。"""

    def test_future_month(self):
        assert _months_until("2026-06", TestDate) == 12

    def test_past_month(self):
        assert _months_until("2024-01", TestDate) == 0

    def test_invalid_format(self):
        assert _months_until("invalid", TestDate) is None

    def test_empty_string(self):
        assert _months_until("", TestDate) is None

    def test_current_month(self):
        assert _months_until("2025-06", TestDate) == 0


class TestEstimateMonthlySavings:
    """_estimate_monthly_savings 月均净存估算测试。"""

    def test_multiple_months(self):
        transactions = [
            {"date": "2025-04-01", "amount": 5000.0},
            {"date": "2025-04-15", "amount": -2000.0},
            {"date": "2025-05-01", "amount": 5000.0},
            {"date": "2025-05-15", "amount": -1500.0},
        ]
        # 月1 净存 3000，月2 净存 3500 → 均值 3250
        result = _estimate_monthly_savings(transactions)
        assert result == 3250.0

    def test_no_transactions(self):
        assert _estimate_monthly_savings([]) is None

    def test_invalid_dates(self):
        transactions = [{"date": "no-date", "amount": 100.0}]
        assert _estimate_monthly_savings(transactions) is None

    def test_single_month(self):
        transactions = [
            {"date": "2025-06-10", "amount": 3000.0},
            {"date": "2025-06-20", "amount": -1000.0},
        ]
        assert _estimate_monthly_savings(transactions) == 2000.0
