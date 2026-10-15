"""技能定时动作（设置 → Agent → 技能 action）的行为锁定。

覆盖：
- 动作校验：合法形状通过；时间/星期/prompt 非法一律拒绝（不静默篡改）
- 保存清洗：非法动作剔除 + 回报 warning，其余配置照常保存
- 调度同步：启用+合法 → 建 job；停用/删除/非法 → 不建；重复同步幂等
- 立即触发：走问答管线归档到 skill:<id>（skip_session），失败分支如实报错
- 保存容错：排程同步失败不影响保存本身
"""

from __future__ import annotations

import json

import pytest
from app import agent_config, db, scheduler


class FakeScheduler:
    """最小假调度器：支持 add_job / remove_all_jobs / get_jobs / remove_job（同步幂等用）。"""

    class _Job:
        def __init__(self, jid: str) -> None:
            self.id = jid

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}

    def remove_all_jobs(self) -> None:
        self.jobs.clear()

    def get_jobs(self) -> list[FakeScheduler._Job]:
        return [self._Job(jid) for jid in self.jobs]

    def remove_job(self, jid: str) -> None:
        self.jobs.pop(jid, None)

    def add_job(self, fn, trigger=None, **kw) -> None:
        jid = kw.get("id", "unknown")
        trig = "cron" if trigger is not None and not isinstance(trigger, str) else (trigger or "interval")
        self.jobs[jid] = {"fn": fn, "trigger": trig, "args": kw.get("args")}


async def _set_skill(skill_id: str, **fields) -> None:
    cfg = await agent_config.get_config()
    skills = cfg.setdefault("skills", {})
    skills[skill_id] = {"name": fields.pop("name", skill_id), "description": "", "enabled": True, **fields}
    await db.set_setting("agent_config", json.dumps(cfg, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 1) 动作校验
# ---------------------------------------------------------------------------


def test_normalize_action_accepts_valid() -> None:
    a = agent_config.normalize_skill_action({"prompt": "检查持仓集中度", "time": "20:30", "weekdays": [6, 0, 0]})
    assert a == {"prompt": "检查持仓集中度", "time": "20:30", "weekdays": [0, 6]}  # 去重 + 排序


def test_normalize_action_defaults_to_daily() -> None:
    """weekdays 缺省/空 = 每天。"""
    assert agent_config.normalize_skill_action({"prompt": "晨间提醒", "time": "08:00"}) == {
        "prompt": "晨间提醒",
        "time": "08:00",
        "weekdays": [],
    }


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "not-a-dict",
        {"prompt": "", "time": "08:00"},  # prompt 空
        {"prompt": "x" * 201, "time": "08:00"},  # prompt 超长
        {"prompt": "ok", "time": "25:99"},  # 时间越界
        {"prompt": "ok", "time": "8:00"},  # 非 HH:MM
        {"prompt": "ok", "time": "08:00", "weekdays": [7]},  # 星期越界
        {"prompt": "ok", "time": "08:00", "weekdays": ["mon"]},  # 非整数
        {"prompt": "ok", "time": "08:00", "weekdays": True},  # 非数组
    ],
)
def test_normalize_action_rejects_invalid(bad) -> None:
    assert agent_config.normalize_skill_action(bad) is None


# ---------------------------------------------------------------------------
# 2) 保存清洗（非法动作剔除 + warning）
# ---------------------------------------------------------------------------


def test_clean_config_drops_bad_action_with_warning() -> None:
    cfg = {
        "skills": {
            "good": {"name": "好技能", "enabled": True, "action": {"prompt": "p", "time": "09:00"}},
            "bad": {"name": "坏技能", "enabled": True, "action": {"prompt": "p", "time": "9:00"}},
        }
    }
    clean, warnings = agent_config.clean_config(cfg)
    assert "action" in clean["skills"]["good"]
    assert "action" not in clean["skills"]["bad"]
    assert len(warnings) == 1 and "坏技能" in warnings[0]
    # 不修改调用方对象
    assert cfg["skills"]["bad"]["action"] is not None


def test_clean_config_none_action_clears_silently() -> None:
    """action=None 是显式清空：不算 warning。"""
    cfg = {"skills": {"s": {"name": "s", "enabled": True, "action": None}}}
    clean, warnings = agent_config.clean_config(cfg)
    assert "action" not in clean["skills"]["s"] and warnings == []


# ---------------------------------------------------------------------------
# 3) 调度同步（幂等 + 停用摘除）
# ---------------------------------------------------------------------------


async def test_sync_skill_jobs_builds_and_is_idempotent(temp_db, monkeypatch) -> None:
    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "_sched", fake)
    await _set_skill("weekly_check", name="定投提醒", enabled=True, action={"prompt": "检查定投", "time": "20:00", "weekdays": [6]})
    await _set_skill("plain", name="无动作技能", enabled=True)

    await scheduler.sync_skill_jobs()
    assert "skill_action:weekly_check" in fake.jobs
    assert "skill_action:plain" not in fake.jobs  # 无动作不排程
    assert fake.jobs["skill_action:weekly_check"]["trigger"] == "cron"
    assert fake.jobs["skill_action:weekly_check"]["args"] == ["weekly_check"]

    # 幂等：再同步一次，job 数不变（先清后建）
    n = len(fake.jobs)
    await scheduler.sync_skill_jobs()
    assert len(fake.jobs) == n


async def test_sync_skill_jobs_removes_disabled_and_invalid(temp_db, monkeypatch) -> None:
    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "_sched", fake)
    await _set_skill("s1", enabled=True, action={"prompt": "p", "time": "09:00"})
    await scheduler.sync_skill_jobs()
    assert "skill_action:s1" in fake.jobs

    # 停用 → 摘除
    await _set_skill("s1", enabled=False, action={"prompt": "p", "time": "09:00"})
    await scheduler.sync_skill_jobs()
    assert "skill_action:s1" not in fake.jobs

    # 启用但动作非法（绕过 API 直接写库）→ 不排程
    await _set_skill("s1", enabled=True, action={"prompt": "p", "time": "99:99"})
    await scheduler.sync_skill_jobs()
    assert "skill_action:s1" not in fake.jobs

    # 删除技能 → 摘除
    await _set_skill("s1", enabled=True, action={"prompt": "p", "time": "09:00"})
    await scheduler.sync_skill_jobs()
    assert "skill_action:s1" in fake.jobs
    cfg = await agent_config.get_config()
    del cfg["skills"]["s1"]
    await db.set_setting("agent_config", json.dumps(cfg, ensure_ascii=False))
    await scheduler.sync_skill_jobs()
    assert "skill_action:s1" not in fake.jobs


# ---------------------------------------------------------------------------
# 4) 立即触发（归档 + 失败分支）
# ---------------------------------------------------------------------------


async def test_run_skill_action_archives(temp_db) -> None:
    await _set_skill("runme", name="立即触发", enabled=True, action={"prompt": "帮我看看这个月的支出", "time": "09:00"})
    out = await scheduler.run_skill_action("runme")
    assert out["ok"] is True
    assert out["thread_id"] == "skill:runme"
    assert out["answer"]

    runs = await db.list_runs("skill:runme", 10)
    assert len(runs) == 1
    assert runs[0]["question"] == "帮我看看这个月的支出"
    # skip_session：不建会话
    sessions = await db.list_sessions()
    assert all(s["thread_id"] != "skill:runme" for s in sessions)


@pytest.mark.parametrize(
    ("skill_id", "setup", "expect"),
    [
        ("missing", None, "不存在"),
        ("disabled", {"enabled": False}, "停用"),
        ("no_action", {"enabled": True}, "没有可执行"),
    ],
)
async def test_run_skill_action_error_branches(temp_db, skill_id, setup, expect) -> None:
    if setup is not None:
        await _set_skill(skill_id, **setup)
    with pytest.raises(ValueError, match=expect):
        await scheduler.run_skill_action(skill_id)


# ---------------------------------------------------------------------------
# 5) API 层：保存清洗回报 + 立即触发端点 + 保存容错
# ---------------------------------------------------------------------------


async def test_api_save_reports_warnings_and_syncs() -> None:
    """保存接口：坏动作 → warnings 回报；调度同步被调用。"""
    from app import main

    called: list[str] = []

    async def _spy() -> None:
        called.append("sync")

    import app.scheduler as sched_mod

    orig = sched_mod.sync_skill_jobs
    sched_mod.sync_skill_jobs = _spy  # type: ignore[assignment]
    try:
        cfg = {
            "version": "2.0",
            "agents": {},
            "skills": {
                "x": {"name": "坏", "enabled": True, "action": {"prompt": "p", "time": "9:00"}},
            },
            "defaults": {},
        }
        out = await main.update_agent_config({"config": cfg})
    finally:
        sched_mod.sync_skill_jobs = orig  # type: ignore[assignment]
    assert out["ok"] is True and out["warnings"]
    assert called == ["sync"]


async def test_api_save_survives_scheduler_sync_failure() -> None:
    """排程同步失败不影响保存本身（保存是数据，排程是运行时）。"""
    import app.scheduler as sched_mod
    from app import main

    async def _boom() -> None:
        raise RuntimeError("scheduler down")

    orig = sched_mod.sync_skill_jobs
    sched_mod.sync_skill_jobs = _boom  # type: ignore[assignment]
    try:
        out = await main.update_agent_config({"config": {"version": "2.0", "agents": {}, "skills": {}, "defaults": {}}})
    finally:
        sched_mod.sync_skill_jobs = orig  # type: ignore[assignment]
    assert out["ok"] is True
