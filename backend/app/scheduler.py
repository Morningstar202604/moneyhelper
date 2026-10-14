"""定时任务（APScheduler）：每日晨报 + 订阅到期巡检。

- 报告时间存 settings.report_time（HH:MM），保存设置后立即重排。
- 报告走同一条问答服务（确定性模板或模型），归档 thread_id='cron'。
- 订阅到期巡检：每天检查 subscriptions，7 天内到期的写入一条 user_memory
  （kind=subscription_due），前端在总览/设置记忆页用到；本月已提醒过的不再重复写。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, service
from .logging_utils import get_logger
from .provenance import record_provenance

log = get_logger(__name__)

REPORT_QUESTION = "帮我做一次全面体检：汇总我的组合、账本与财务目标的现状，只描述事实与风险提示，不给操作建议。"
# 订阅到期提前提醒天数；due_day 在 [today, today+SUBS_REMIND_WITHIN_DAYS] 区间内即生成提醒
SUBS_REMIND_WITHIN_DAYS = 7

_sched: AsyncIOScheduler | None = None
_state: dict[str, Any] = {
    "enabled": False,
    "report_time": "08:00",
    "last_run_at": None,
    "next_run_at": None,
    "last_error": None,
    "generated": 0,
}


def _parse_time(value: str | None) -> tuple[int, int] | None:
    if not value or ":" not in value:
        return None
    try:
        h, m = value.strip().split(":")
        hh, mm = int(h), int(m)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        return hh, mm
    except (ValueError, TypeError):
        return None


async def has_data() -> bool:
    """库中是否已有持仓或流水（空库不生成无意义的晨报）。"""
    if await db.list_positions():
        return True
    return bool(await db.fetch_all("SELECT 1 FROM transactions LIMIT 1"))


async def generate_report() -> dict[str, Any]:
    """生成一次晨报并归档。手动触发（POST /api/reports/generate）与定时共用。

    空库时返回 skipped=True 并跳过归档：无内容的定时产出只是噪音。
    """
    async def emit(e: dict[str, Any]) -> None:
        pass

    if not await has_data():
        return {
            "skipped": True,
            "reason": "no_data",
            "answer": "",
            "level": "",
            "flags": [],
        }

    try:
        result = await service.run_question(REPORT_QUESTION, emit)
        await db.save_run(
            thread_id="cron",
            question=REPORT_QUESTION,
            answer=result["answer"],
            level=result["level"],
            flags=result["flags"],
            route=result.get("route", ""),
            llm=result.get("llm", ""),
            route_reason=result.get("route_reason", ""),
            # 系统归档不进会话列表：晨报历史按 thread_id='cron' 从 runs 读取
            skip_session=True,
        )
        _state["generated"] += 1
        _state["last_run_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _state["last_error"] = None
        # 记录晨报生成审计：审计失败不应把已生成的晨报标成失败
        try:
            await record_provenance(
                action="generate_morning_report",
                entity_type="report",
                entity_id="morning_report",
                before=None,
                after={"generated": _state["generated"], "thread_id": "cron"},
                source="scheduler",
                username="system",
            )
        except Exception as audit_exc:  # noqa: BLE001
            log.warning("morning report audit failed: %s", audit_exc)
        return result
    except Exception as exc:  # noqa: BLE001 — 晨报失败只记录，不炸服务
        _state["last_error"] = f"{type(exc).__name__}: {exc}"
        raise


async def _check_subscriptions_due() -> None:
    """检查 subscriptions.due_day：7 天内到期的写入 user_memory（kind=subscription_due）。
    每个自然月只写一条提醒（due_day 列表拼接），避免每日重复刷屏。"""
    subs = await db.list_subscriptions()
    if not subs:
        return
    today = datetime.now().astimezone().date()
    soon: list[dict[str, Any]] = []
    for s in subs:
        dd = (s.get("due_day") or "").strip()
        if not dd.isdigit():
            continue
        due_day = int(dd)
        if due_day < 1 or due_day > 31:
            continue
        # 本月 upcoming due date：取 [today, today+WINDOW] 区间内第一个合法的 due_day
        due_date = _upcoming_due_date(today, due_day)
        if due_date is None:
            continue
        days_until = (due_date - today).days
        if 0 <= days_until <= SUBS_REMIND_WITHIN_DAYS:
            soon.append(
                {
                    "name": s["name"],
                    "monthly": float(s.get("monthly") or 0),
                    "note": s.get("note", ""),
                    "due_day": due_day,
                    "due_date": due_date.isoformat(),
                    "days_until": days_until,
                }
            )
    if not soon:
        return
    soon.sort(key=lambda x: x["days_until"])
    month_key = today.strftime("%Y-%m")
    marker = f"subscription_due:{month_key}"
    # 本月首次写：先清旧月的同 marker，再写入（保证内容随 today 刷新但只保留一条）
    await db.delete_memory_by_kind(marker)
    total = 0.0
    bullets: list[str] = []
    for s_n in soon:
        when = "今天" if s_n["days_until"] == 0 else f"{s_n['days_until']} 天后"
        bullet = f"- **{s_n['name']}**：{s_n['monthly']:.2f} 元 / 月，{s_n['due_day']} 号扣款（{due_date_cn(s_n['due_date'])}，{when}）"
        if s_n["note"]:
            bullet += f" · {s_n['note']}"
        bullets.append(bullet)
        total += s_n["monthly"]
    content = "\n".join(
        [
            f"## 本月待缴订阅（{month_key}）",
            f"> 内部标记：{marker}",
            "",
            *bullets,
            "",
            f"**小计**：{len(soon)} 笔待缴，月度合计 {total:.2f} 元 / 月",
        ]
    )
    await db.add_memory(content, kind=marker)


def _upcoming_due_date(today, due_day: int) -> Any:
    """返回 upcomingdue date（本月或下月），限定在 today+WINDOW 内；None 表示不在窗口。"""
    candidate_this_month = _safe_date(today.year, today.month, due_day)
    window_end = today + timedelta(days=SUBS_REMIND_WITHIN_DAYS)
    if candidate_this_month is not None and today <= candidate_this_month <= window_end:
        return candidate_this_month
    # 下月候选
    y, m = today.year, today.month
    m2 = m + 1
    y2 = y
    if m2 > 12:
        m2 = 1
        y2 = y + 1
    candidate_next = _safe_date(y2, m2, due_day)
    if candidate_next is not None and today <= candidate_next <= window_end:
        return candidate_next
    return None


def _safe_date(year: int, month: int, day: int):
    from datetime import date as _date
    try:
        return _date(year, month, day)
    except ValueError:
        return None


def due_date_cn(iso: str) -> str:
    try:
        from datetime import date as _date
        d = _date.fromisoformat(iso)
        return f"{d.month} 月 {d.day} 日"
    except Exception:
        return iso


def _reschedule() -> None:
    global _sched
    if _sched is None:
        return
    _sched.remove_all_jobs()
    # skill 开关（设置→Agent）真正生效：morning_report 关闭时不再注册定时晨报
    # （手动「生成今日晨报」走 action 路径，不受影响）
    if not _state.get("report_enabled", True):
        _state["next_run_at"] = "（晨报已在设置中关闭）"
        return
    hm = _parse_time(_state.get("report_time"))
    if hm is None:
        _sched.add_job(_cron_job, trigger="interval", minutes=1440, id="morning_report")
        _state["next_run_at"] = "（周期 24h 兜底）"
        return
    h, m = hm
    _sched.add_job(_cron_job, CronTrigger(hour=h, minute=m, timezone="Asia/Shanghai"), id="morning_report")
    _sched.add_job(_check_subscriptions_due, CronTrigger(hour=h, minute=m, timezone="Asia/Shanghai"), id="subs_due_check")
    _state["next_run_at"] = f"每天 {h:02d}:{m:02d}"


async def _cron_job() -> None:
    try:
        await generate_report()
    except Exception as exc:  # noqa: BLE001
        # 不能让静默吞异常导致晨报连续失败 N 天无感知
        log.exception("cron job failed: %s", exc)
        _state["last_error"] = f"晨报生成失败: {exc}"
        _state["last_run_at"] = datetime.now().isoformat()


async def notify_settings_changed() -> None:
    """设置保存后调用：读最新报告时间与晨报开关，并重排。"""
    st = await db.get_settings()
    _state["report_time"] = st.get("report_time", "08:00")
    try:
        from . import agent_config

        _state["report_enabled"] = await agent_config.is_skill_enabled("morning_report")
    except Exception:  # noqa: BLE001 — 配置读取失败按开启处理（宁多报不漏报）
        _state["report_enabled"] = True
    _reschedule()


async def start() -> None:
    global _sched
    if _sched is not None:
        return
    st = await db.get_settings()
    _state["report_time"] = st.get("report_time", "08:00")
    try:
        from . import agent_config

        _state["report_enabled"] = await agent_config.is_skill_enabled("morning_report")
    except Exception:  # noqa: BLE001
        _state["report_enabled"] = True
    _sched = AsyncIOScheduler(timezone="Asia/Shanghai")
    _reschedule()
    _sched.start()
    _state["enabled"] = True


async def stop() -> None:
    global _sched
    if _sched is not None:
        _sched.shutdown(wait=False)
    _sched = None
    _state["enabled"] = False


def status() -> dict[str, Any]:
    return {
        "enabled": _state["enabled"],
        "report_time": _state.get("report_time", "08:00"),
        "last_run_at": _state["last_run_at"],
        "next_run_at": _state["next_run_at"],
        "last_error": _state["last_error"],
        "generated": _state["generated"],
    }
