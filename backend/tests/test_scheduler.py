"""定时晨报 scheduler 测试：时间解析、空库跳过、生成成功/失败、重排、生命周期。

目标：把 scheduler.py 覆盖从 51% 拉上来（调度/失败路径是易回归层）。
"""

from __future__ import annotations

import pytest
from app import db, scheduler, service

# ---------------------------------------------------------------------------
# _parse_time：合法/非法边界
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("08:00", (8, 0)),
        ("23:59", (23, 59)),
        ("00:00", (0, 0)),
        (" 09:30 ", (9, 30)),
    ],
)
def test_parse_time_valid(raw, expected):
    assert scheduler._parse_time(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "0800", "25:00", "08:60", "8", "a:b", "8:00:00"],
)
def test_parse_time_invalid(raw):
    assert scheduler._parse_time(raw) is None


# ---------------------------------------------------------------------------
# has_data：持仓/流水存在判定
# ---------------------------------------------------------------------------


async def test_has_data_true_with_seed(temp_db):
    assert await scheduler.has_data() is True


async def test_has_data_false_when_empty(temp_db, monkeypatch):
    # 模拟空库：无持仓且无流水（async mock）
    async def _no_positions():
        return []

    async def _no_rows(*a, **k):
        return []

    monkeypatch.setattr(db, "list_positions", _no_positions)
    monkeypatch.setattr(db, "fetch_all", _no_rows)
    assert await scheduler.has_data() is False


# ---------------------------------------------------------------------------
# generate_report：空库跳过 / 成功归档 / 失败记录
# ---------------------------------------------------------------------------


async def test_generate_report_skips_when_empty(temp_db, monkeypatch):
    async def _no() -> bool:
        return False

    monkeypatch.setattr(scheduler, "has_data", _no)
    out = await scheduler.generate_report()
    assert out["skipped"] is True
    assert out["reason"] == "no_data"


async def test_generate_report_success_archives(temp_db, monkeypatch):
    async def fake_run_question(q, emit, **kw):
        await emit({"type": "final"})
        return {
            "answer": "你的组合总体稳健。",
            "level": "L1 洞察",
            "route": "market",
            "llm": "template",
            "route_reason": "测试",
            "flags": [],
        }

    monkeypatch.setattr(service, "run_question", fake_run_question)
    before = scheduler._state["generated"]
    out = await scheduler.generate_report()
    assert out["answer"] == "你的组合总体稳健。"
    # 模块级计数是全局的，用相对增量断言（全量运行时其它用例可能已累加）
    assert scheduler._state["generated"] == before + 1
    assert scheduler._state["last_error"] is None
    assert scheduler._state["last_run_at"] is not None
    # 已归档（runs 表 thread_id=cron）
    runs = await db.fetch_all("SELECT * FROM runs WHERE thread_id='cron'")
    assert len(runs) >= 1


async def test_generate_report_records_failure(temp_db, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("quotes down")

    monkeypatch.setattr(service, "run_question", boom)
    with pytest.raises(RuntimeError, match="quotes down"):
        await scheduler.generate_report()
    assert "RuntimeError" in (scheduler._state["last_error"] or "")


# ---------------------------------------------------------------------------
# 重排与生命周期
# ---------------------------------------------------------------------------


async def test_reschedule_invalid_time_falls_back_to_interval(temp_db, monkeypatch):
    monkeypatch.setattr(scheduler, "_sched", FakeScheduler())
    scheduler._state["report_time"] = "99:99"
    scheduler._reschedule()
    job = scheduler._sched.jobs.get("morning_report")
    assert job is not None
    assert job["trigger"] == "interval"
    assert scheduler._state["next_run_at"] == "（周期 24h 兜底）"


async def test_reschedule_valid_time_uses_cron(temp_db, monkeypatch):
    monkeypatch.setattr(scheduler, "_sched", FakeScheduler())
    scheduler._state["report_time"] = "08:30"
    scheduler._reschedule()
    job = scheduler._sched.jobs.get("morning_report")
    assert job is not None
    assert job["trigger"] == "cron"
    assert scheduler._state["next_run_at"] == "每天 08:30"


async def test_start_stop_status(temp_db):
    await scheduler.start()
    try:
        assert scheduler._state["enabled"] is True
        st = scheduler.status()
        assert st["enabled"] is True
        assert st["report_time"] == "08:00"
    finally:
        await scheduler.stop()
    assert scheduler._state["enabled"] is False


class _FakeJob:
    """假 job 对象：只有 sync_skill_jobs 用到的 id（判前缀用）。"""

    def __init__(self, jid: str) -> None:
        self.id = jid


class FakeScheduler:
    """最小假调度器：记录 add_job / remove_all_jobs，并支持 get_jobs/remove_job。

    get_jobs/remove_job 是 sync_skill_jobs()（技能定时动作同步）依赖的接口——
    2026-10 新增技能调度后需要，缺了会让所有走到同步逻辑的用例报 AttributeError。
    """

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}

    def remove_all_jobs(self) -> None:
        self.jobs.clear()

    def get_jobs(self) -> list:
        return [_FakeJob(jid) for jid in self.jobs]

    def remove_job(self, jid: str) -> None:
        self.jobs.pop(jid, None)

    def add_job(self, fn, trigger=None, **kw) -> None:
        jid = kw.get("id", "morning_report")
        # interval 分支传字符串 "interval"；cron 分支传 CronTrigger 实例
        if isinstance(trigger, str):
            trig = trigger
        elif trigger is None:
            trig = "interval"
        else:
            trig = "cron"
        self.jobs[jid] = {"fn": fn, "trigger": trig}


async def test_notify_settings_changed_reschedules(temp_db, monkeypatch):
    monkeypatch.setattr(scheduler, "_sched", FakeScheduler())
    # 改设置里的报告时间
    await db.set_setting("report_time", "22:10")
    scheduler._state["report_time"] = "09:00"
    await scheduler.notify_settings_changed()
    assert scheduler._state["report_time"] == "22:10"
    job = scheduler._sched.jobs.get("morning_report")
    assert job is not None and job["trigger"] == "cron"