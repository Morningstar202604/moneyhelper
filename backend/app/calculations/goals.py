"""目标进度确定性计算：每个状态的 on_track 纯代码判断，不涉及 LLM。

与 analysis.py goal_progress 互补：本模块返回结构化 GoalProgress（含确定性 on_track 判断），
analysis.py 的 goal_progress 返回更轻量的字典列表供现有 API 复用。

数据格式（与 db.py / analysis.py 现有结构一致）：
- goals:       [{"name", "target", "saved", "monthly_contribution", "deadline(YYYY-MM)"}, ...]
- positions:   [{"name", "shares", "last", "kind"}, ...] — 用于计算当前持仓可变现价值
- transactions:[{"date(YYYY-MM-DD)", "amount", "category"}, ...] — 用于计算历史月均净存
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass
class GoalProgress:
    """单个财务目标的进度评估结果。"""
    name: str                    # 目标名称
    target_amount: float         # 目标金额（元）
    current_amount: float        # 当前已存（元）
    monthly_contribution: float  # 每月计划存入（元）
    months_remaining: int | None  # 距截止月剩余月数（None 表示无截止日期）
    on_track: bool               # 是否按进度达标（确定性判断）
    required_monthly: float | None  # 要达到目标所需的月存金额（None 表示已完成或无法计算）
    progress_pct: float          # 当前进度百分比


def calculate_goal_progress(
    goals: list[dict[str, Any]],
    positions: list[dict[str, Any]] | None = None,
    transactions: list[dict[str, Any]] | None = None,
    *,
    as_of: date | None = None,
) -> list[GoalProgress]:
    """计算每个目标的进度，确定性判断 on_track。

    on_track 判断逻辑：
    1. 已完成目标（current >= target）→ on_track = True
    2. 无截止日期的目标 → 按当前月存推进，on_track = (monthly_contribution > 0 或 current > 0)
    3. 有截止日期的目标 → 计算 required_monthly = (target - current) / months_remaining，
       on_track = (monthly_contribution >= required_monthly)

    Args:
        goals:        目标列表
        positions:    持仓列表（用于计算可用于目标的可变现金额，可选）
        transactions: 交易列表（用于估算实际月均净存，可选）
        as_of:        评估日期，默认今天

    Returns:
        GoalProgress 列表（按 goal 原始顺序）
    """
    today = as_of or date.today()

    # 计算实际月均净存（从 transactions 推算）
    actual_monthly_net = _estimate_monthly_savings(transactions) if transactions else None

    results: list[GoalProgress] = []
    for g in goals:
        target = float(g.get("target", 0))
        saved = float(g.get("saved", 0))
        planned_monthly = float(g.get("monthly_contribution", 0))

        # 进度百分比
        progress_pct = round(saved / target * 100, 1) if target > 0 else 0.0

        # 剩余月数
        months_remaining = None
        deadline_str = str(g.get("deadline", "") or "").strip()
        if deadline_str:
            months_remaining = _months_until(deadline_str, today)

        # 所需月存
        remaining_amount = max(0.0, target - saved)
        if remaining_amount <= 0:
            # 已达成
            results.append(GoalProgress(
                name=g.get("name", ""),
                target_amount=round(target, 2),
                current_amount=round(saved, 2),
                monthly_contribution=round(planned_monthly, 2),
                months_remaining=months_remaining,
                on_track=True,
                required_monthly=None,
                progress_pct=progress_pct,
            ))
            continue

        if months_remaining is not None and months_remaining > 0:
            required = round(remaining_amount / months_remaining, 2)
        elif months_remaining is not None and months_remaining <= 0:
            # 已逾期且未达成
            results.append(GoalProgress(
                name=g.get("name", ""),
                target_amount=round(target, 2),
                current_amount=round(saved, 2),
                monthly_contribution=round(planned_monthly, 2),
                months_remaining=0,
                on_track=False,
                required_monthly=None,
                progress_pct=progress_pct,
            ))
            continue
        else:
            # 无截止日期
            required = None

        # on_track 判断
        if required is not None:
            # 有明确所需月存：用实际净存或计划月存做比较
            effective_monthly = actual_monthly_net if actual_monthly_net is not None else planned_monthly
            on_track = effective_monthly >= required
        else:
            # 无截止日期：只要每月有在存或总进度正向
            on_track = planned_monthly > 0 or saved > 0

        results.append(GoalProgress(
            name=g.get("name", ""),
            target_amount=round(target, 2),
            current_amount=round(saved, 2),
            monthly_contribution=round(planned_monthly, 2),
            months_remaining=months_remaining,
            on_track=on_track,
            required_monthly=required,
            progress_pct=progress_pct,
        ))

    return results


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------

def _months_until(deadline: str, today: date) -> int | None:
    """计算从 today 到 deadline (YYYY-MM) 的月份差。

    返回 0 表示已逾期（deadline 月早于当前月）。
    """
    if not deadline or len(deadline) != 7:
        return None
    try:
        ym = datetime.strptime(deadline, "%Y-%m")
        months = (ym.year - today.year) * 12 + (ym.month - today.month)
        return max(0, months)
    except ValueError:
        return None


def _estimate_monthly_savings(transactions: list[dict[str, Any]]) -> float | None:
    """从交易记录估算月均净存（收入 - 支出）。"""
    if not transactions:
        return None

    # 按月聚合净存（严格校验 YYYY-MM 前缀格式）
    monthly_net: dict[str, float] = {}
    for t in transactions:
        date_str = str(t.get("date", ""))
        if len(date_str) >= 7:
            month = date_str[:7]
            # 验证第 4 位是 '-' 且月份可解析（如 "2025-06"）
            if month[4] != "-":
                continue
            try:
                int(month[:4])
                m = int(month[5:])
                if m < 1 or m > 12:
                    continue
            except (ValueError, IndexError):
                continue
            amount = float(t.get("amount", 0))
            monthly_net[month] = monthly_net.get(month, 0.0) + amount

    if not monthly_net:
        return None

    avg = sum(monthly_net.values()) / len(monthly_net)
    return round(avg, 2)
