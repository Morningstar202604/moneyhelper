"""净值追踪：持仓市值 + 现金 - 负债 = 净值。

纯函数，输入为解耦的数据结构（不依赖 db/quotes 层），方便单测与复用。

数据格式（与 analysis.py / db.py 一致）：
- positions:    [{"symbol", "name", "kind", "shares", "last"}, ...]
- cash:         [{"name", "amount"}, ...]          — 现金账户
- debts:        [{"name", "balance", "rate", "monthly"}, ...]
- subscriptions:[{"name", "monthly"}, ...]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class NetWorthSnapshot:
    """某一时刻的净值快照。"""
    date: date
    total_assets: float       # 总资产（持仓市值 + 现金）
    total_liabilities: float  # 总负债（贷款本金 + 信用卡欠款）
    net_worth: float          # 净值 = 总资产 - 总负债
    asset_breakdown: dict[str, float] = field(default_factory=dict)   # 资产明细
    liability_breakdown: dict[str, float] = field(default_factory=dict)  # 负债明细


def _round(value: float) -> float:
    return round(value, 2)


def calculate_net_worth(
    positions: list[dict[str, Any]],
    cash: list[dict[str, Any]] | None = None,
    debts: list[dict[str, Any]] | None = None,
    subscriptions: list[dict[str, Any]] | None = None,
    *,
    as_of: date | None = None,
) -> NetWorthSnapshot:
    """计算当前净值快照。

    Args:
        positions:     持仓列表（需含 shares, last 字段；kind 字段区分现金类持仓）
        cash:          现金账户列表（需含 amount 字段），为空时使用 positions 中 kind="现金"
        debts:         负债列表（需含 balance 字段，可选 interest_accrued）
        subscriptions: 订阅列表（仅用于显示未来支出提示，不计入负债）
        as_of:         快照日期，默认为今天

    Returns:
        NetWorthSnapshot 含完整的资产/负债明细

    Raises:
        ValueError: 输入含负数 shares 等非法值
    """
    today = as_of or date.today()

    # --- 资产：持仓市值 ---
    asset_breakdown: dict[str, float] = {}
    total_assets = 0.0
    for p in positions:
        shares = float(p.get("shares", 0))
        price = float(p.get("last", 0))
        if shares < 0:
            raise ValueError(f"持仓份额不能为负: {p.get('name', p.get('symbol', '?'))} = {shares}")
        if price < 0:
            raise ValueError(f"价格不能为负: {p.get('name', p.get('symbol', '?'))} = {price}")
        mv = shares * price
        label = p.get("name") or p.get("symbol") or "未知"
        asset_breakdown[label] = _round(mv)
        total_assets += mv

    # --- 资产：现金账户（如果传入独立 cash 列表） ---
    if cash:
        for c in cash:
            amt = float(c.get("amount", 0))
            if amt < 0:
                raise ValueError(f"现金余额不能为负: {c.get('name', '?')} = {amt}")
            label = c.get("name") or "现金"
            asset_breakdown[label] = _round(amt)
            total_assets += amt

    total_assets = _round(total_assets)

    # --- 负债：贷款 + 信用卡 ---
    liability_breakdown: dict[str, float] = {}
    total_liabilities = 0.0
    for d in (debts or []):
        balance = float(d.get("balance", 0))
        interest = float(d.get("interest_accrued", 0))
        total = balance + interest
        if total < 0:
            raise ValueError(f"负债总额不能为负: {d.get('name', '?')} = {total}")
        label = d.get("name") or "未知负债"
        liability_breakdown[label] = _round(total)
        total_liabilities += total

    total_liabilities = _round(total_liabilities)
    net_worth = _round(total_assets - total_liabilities)

    return NetWorthSnapshot(
        date=today,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=net_worth,
        asset_breakdown=asset_breakdown,
        liability_breakdown=liability_breakdown,
    )
