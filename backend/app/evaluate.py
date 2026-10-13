"""规则驱动的"首页评估层"：聚合预算/订阅/债务/目标/现金流信号，生成结构化行动项。

完全确定性，不依赖 LLM。每个 Rule 是纯函数：inputs → list[EvalItem]。
前端 GET /api/evaluate 调用，首页 SmartEvalCard 按优先级渲染。

每条 EvalItem:
- kind: "todo"（需要用户操作）/ "warn"（告警）/ "info"（提示）/ "goal"（目标）
- priority: 0（最高，必须处理）/ 1（建议处理）/ 2（可延后）/ 3（仅提示）
- code: 规则编码（i18n key 前缀）
- title / detail: i18n key + {vars}
- action: 可选跳转路径（前端据此渲染按钮）
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from . import db, scheduler

# 与 scheduler.py 中的订阅到期窗口保持一致
SUBS_REMIND_WITHIN_DAYS = getattr(scheduler, "SUBS_REMIND_WITHIN_DAYS", 7)


@dataclass
class EvalItem:
    kind: str           # todo / warn / info / goal
    priority: int       # 0..3
    code: str           # i18n key: eval.<code>.title / eval.<code>.detail
    title: str = ""     # 缺省回退（i18n 失败时用）
    detail: str = ""
    vars: dict[str, Any] = field(default_factory=dict)
    action: dict[str, str] | None = None  # {"path": "/settings#budget", "label": "..."}

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self)}


# --------------------------------------------------------------------------
# 日期 / 金额工具
# --------------------------------------------------------------------------

def _month_str(d: date | None = None) -> str:
    return (d or date.today()).strftime("%Y-%m")


def _days_in_month(d: date) -> int:
    m = d.month
    y = d.year
    if m == 12:
        return (date(y + 1, 1, 1) - date(y, m, 1)).days
    return (date(y, m + 1, 1) - date(y, m, 1)).days


def _safe_int(s: str) -> int | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(re.sub(r"\s+", "", s))
    except (TypeError, ValueError):
        return None


def _upcoming_due(today: date, due_day_raw: str, *, window: int) -> tuple[int, date] | None:
    """(days_until, due_date) or None（不在窗口内 / due_day 非法）。"""
    if window <= 0:
        window = 7
    n = _safe_int(due_day_raw)
    if n is None or n <= 0:
        return None

    def on_month(d: date, day: int) -> date | None:
        last = _days_in_month(d)
        if day > last:
            return None
        return d.replace(day=day)

    # 本月
    this = on_month(today, n)
    if this and today <= this <= today + timedelta(days=window):
        return ( (this - today).days, this )
    # 下月
    if today.month == 12:
        nxt = today.replace(year=today.year + 1, month=1, day=1)
    else:
        nxt = today.replace(month=today.month + 1, day=1)
    that = on_month(nxt, n)
    if that and today <= that <= today + timedelta(days=window):
        return ( (that - today).days, that )
    return None


# --------------------------------------------------------------------------
# Rules：每条 rule 接收拉取的聚合数据，返回 list[EvalItem]
# --------------------------------------------------------------------------

async def _rule_budget(month: str) -> list[EvalItem]:
    """预算进度：超支 → P0；快超 → P1；没有预算但有流水 → P2。"""
    rows = await db.list_budgets(month)
    usage = await db.budget_usage(month)
    out: list[EvalItem] = []

    total = next((r for r in rows if r.get("category") == "__total"), None)
    if not total or (total.get("amount") or 0) <= 0:
        # 本月是否有流水？（任意一条即可）
        txns = await db.list_transactions()
        if txns:
            out.append(EvalItem(
                kind="info", priority=2, code="budget.missing",
                action={"path": "/settings#budget"},
            ))
        return out

    pct = usage.get("total_pct", 0) if isinstance(usage, dict) else 0
    over = usage.get("over", False) if isinstance(usage, dict) else (pct >= 100)
    if over:
        over_amt = usage.get("total_spent", 0) - (total.get("amount") or 0)
        out.append(EvalItem(
            kind="todo", priority=0, code="budget.over",
            vars={"pct": pct, "over": round(over_amt, 0), "total": total["amount"]},
        ))
    elif pct >= 85:
        left = (total.get("amount") or 0) - usage.get("total_spent", 0)
        out.append(EvalItem(
            kind="warn", priority=1, code="budget.near",
            vars={"pct": pct, "left": round(max(left, 0), 0)},
        ))

    return out


async def _rule_subscriptions(today: date) -> list[EvalItem]:
    """订阅 N 天内到期：P1；无 due_day 的订阅：P3 提示配置。"""
    subs = await db.list_subscriptions()
    out: list[EvalItem] = []
    due_items: list[EvalItem] = []
    missing_due: list[str] = []

    for s in subs:
        due_day = s.get("due_day", "")
        res = _upcoming_due(today, due_day, window=SUBS_REMIND_WITHIN_DAYS)
        if res is not None:
            days, due_date = res
            due_items.append(EvalItem(
                kind="todo", priority=1, code="subs.due.item",
                title=s.get("name", ""),
                detail="",
                vars={
                    "name": s["name"],
                    "monthly": float(s.get("monthly") or 0),
                    "days": days,
                    "date": due_date.strftime("%-m-%-d"),
                },
            ))
        elif not (due_day or "").strip():
            missing_due.append(s["name"])

    if len(due_items) == 1:
        out.append(due_items[0])
    elif len(due_items) > 1:
        # 多条订阅即将扣款：聚合为一条，避免首页信息轰炸
        total_monthly = sum(float(it.vars.get("monthly", 0)) for it in due_items)
        earliest = min(due_items, key=lambda it: it.vars.get("days", 999))
        out.append(EvalItem(
            kind="todo", priority=1, code="subs.due.items",
            vars={
                "n": len(due_items),
                "amount": round(total_monthly, 2),
                "date": earliest.vars.get("date", ""),
            },
        ))

    if missing_due:
        out.append(EvalItem(
            kind="info", priority=3, code="subs.missing_due",
            vars={"n": len(missing_due), "names": ", ".join(missing_due[:5])},
            action={"path": "/settings#subscriptions"},
        ))
    return out


async def _rule_debts(today: date) -> list[EvalItem]:
    """债务 N 天内还款：P1；高利率（>15%）债务：P2 提示优先偿还。"""
    debts = await db.list_debts()
    out: list[EvalItem] = []
    for d in debts:
        due_day = d.get("due_day", "")
        res = _upcoming_due(today, due_day, window=SUBS_REMIND_WITHIN_DAYS)
        if res is not None:
            days, due_date = res
            out.append(EvalItem(
                kind="todo", priority=1,
                code="debt.due.item",
                vars={
                    "name": d["name"],
                    "monthly": d["monthly"],
                    "days": days,
                    "date": due_date.strftime("%-m-%-d"),
                    "balance": d["balance"],
                },
            ))
        rate = float(d.get("rate") or 0)
        # rate 以小数存储（0.18 = 18%），阈值 0.15 = 15%
        if rate >= 0.15:
            out.append(EvalItem(
                kind="info", priority=2, code="debt.high_rate",
                vars={"name": d["name"], "rate": round(rate * 100, 2)},
            ))
    return out


async def _rule_goals(month: str) -> list[EvalItem]:
    """目标 vs 已过月份进度：落后 → P2；deadline 临近 → P1。"""
    goals = await db.list_goals()
    out: list[EvalItem] = []
    try:
        cur_year, cur_month = (int(x) for x in month.split("-"))
    except (TypeError, AttributeError, ValueError):
        cur_year, cur_month = date.today().year, date.today().month

    for g in goals:
        target = float(g.get("target") or 0)
        saved = float(g.get("saved") or 0)
        deadline = (g.get("deadline") or "").strip()
        if target <= 0:
            continue

        pct = round((saved / target) * 100, 1) if target > 0 else 0

        # deadline 临近：目标月份含当月或已逾期
        if deadline:
            try:
                d_year, d_month = (int(x) for x in deadline.split("-"))
                months_total = (d_year - cur_year) * 12 + (d_month - cur_month)
                late = months_total <= 0 and pct < 100
                soon = 0 < months_total <= 2 and pct < 80
                if late:
                    out.append(EvalItem(
                        kind="todo", priority=0, code="goal.deadline_late",
                        vars={"name": g["name"], "pct": pct, "target": target, "saved": saved},
                    ))
                elif soon:
                    out.append(EvalItem(
                        kind="warn", priority=1, code="goal.deadline_soon",
                        vars={"name": g["name"], "pct": pct, "months": months_total},
                    ))
                continue
            except (TypeError, AttributeError, ValueError):
                pass

        # 没有 deadline：按盈亏/节奏提示
        if pct >= 100:
            out.append(EvalItem(
                kind="info", priority=2, code="goal.done",
                vars={"name": g["name"]},
            ))
    return out


async def _rule_cashflow() -> list[EvalItem]:
    """活期现金 < 月度基础支出 × 1.5：P2 提示流动性不足。"""
    # 计算"月基础支出" = 债务月供 + 订阅月度合计
    subs = await db.list_subscriptions()
    debts = await db.list_debts()
    monthly_out = sum(float(s.get("monthly") or 0) for s in subs)
    monthly_out += sum(float(d.get("monthly") or 0) for d in debts)
    if monthly_out <= 0:
        return []

    total_cash = await db.total_cash()
    if total_cash is None:
        return []
    if total_cash < monthly_out * 1.5:
        return [EvalItem(
            kind="warn", priority=2, code="cash.low",
            vars={"cash": round(total_cash, 0), "need": round(monthly_out * 3, 0)},
        )]
    return []


# --------------------------------------------------------------------------
# 入口：evaluate_all(month) -> {items, refreshed_at}
# --------------------------------------------------------------------------

RULES = (
    ("budget",   _rule_budget),
    ("subs",     _rule_subscriptions),
    ("debts",    _rule_debts),
    ("goals",    _rule_goals),
    ("cashflow", _rule_cashflow),
)


async def evaluate_all(month: str | None = None, *, today: date | None = None) -> dict[str, Any]:
    """跑全部规则，返回按 priority 排序后的 items + 元数据。"""
    month = month or _month_str(today)
    today = today or date.today()

    items: list[EvalItem] = []
    for name, fn in RULES:
        try:
            if name == "budget" or name == "goals":
                items += await fn(month)
            elif name == "cashflow":
                items += await fn()
            elif name in ("subs", "debts"):
                items += await fn(today)
            else:
                items += await fn(month)
        except Exception as exc:  # noqa: BLE001 — 任一规则异常不应拖垮评估层
            from .logging_utils import get_logger
            get_logger(__name__).warning("evaluate rule %s failed: %s", name, exc)

    items.sort(key=lambda i: (i.priority, i.kind))
    return {
        "month": month,
        "refreshed_at": datetime.now().isoformat(timespec="seconds"),
        "items": [i.to_dict() for i in items],
        "summary": _summary(items),
    }


def _summary(items: list[EvalItem]) -> dict[str, int]:
    r = {"todo": 0, "warn": 0, "info": 0, "goal": 0, "max_priority": 3}
    for i in items:
        r[i.kind] = r.get(i.kind, 0) + 1
        if i.priority < r["max_priority"]:
            r["max_priority"] = i.priority
    return r
