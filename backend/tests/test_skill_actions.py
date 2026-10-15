"""技能定时动作（设置 → Agent → 技能 action）的行为锁定。

覆盖：
- 动作校验：合法形状通过；时间/星期/prompt 非法一律拒绝（不静默篡改）
- 保存清洗：非法动作剔除 + 回报 warning，其余配置照常保存
- 调度同步：启用+合法 → 建 job；停用/删除/非法 → 不建；重复同步幂等
- 立即触发：走问答管线归档到 skill:<id>（skip_session），失败分支如实报错
- 保存容错：排程同步失败不影响保存本身
- 系统线程隔离：cron / skill:<id> 不进会话列表（写入/读侧/启动迁移三道防线）

注意：本模块所有用例都必须跑在临时库上。曾因两个用例漏挂 temp_db，
经 main.update_agent_config 直接写进开发库、把研发环境 agent_config 清空——
故此处加模块级 autouse 隔离兜底，任何漏挂 temp_db 的用例也不会碰到真实库。
"""

from __future__ import annotations

import json

import pytest
from app import agent_config, db, scheduler


@pytest.fixture(autouse=True)
def _isolated_db(temp_db):
    """模块级兜底：全部用例强制跑在临时库（漏挂 temp_db 也不写研发库）。"""
    return temp_db


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
# 注意：调用 main.update_agent_config 会写 settings 表——必须带 temp_db，
# 否则会直接写进开发库（曾把研发环境 agent_config 清成空配置）。
# ---------------------------------------------------------------------------


async def test_api_save_reports_warnings_and_syncs(temp_db) -> None:
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


async def test_api_save_survives_scheduler_sync_failure(temp_db) -> None:
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


# ---------------------------------------------------------------------------
# 6) 系统归档线程不进会话列表（含启动回填与读侧兜底）
# ---------------------------------------------------------------------------


async def test_system_threads_never_listed_as_sessions(temp_db) -> None:
    """cron / skill:<id> 归档线程不得出现在会话列表；启动迁移也要排除它们。

    回归：skip_session 只拦写入侧，重启时 _migrate_sessions_from_runs 会把系统
    线程当作旧库会话补建出来（真实缺陷）。
    """
    await _set_skill("sys_skill", name="系统线程技能", enabled=True, action={"prompt": "p", "time": "09:00"})
    # 写入两条系统归档 + 一条真实对话
    await db.save_run("cron", "晨报问题", "晨报回答", "已生成", skip_session=True)
    await db.save_run("skill:sys_skill", "技能问题", "技能回答", "L1 洞察", skip_session=True)
    await db.save_run("real-thread", "普通提问", "普通回答", "L1 洞察")

    sessions = await db.list_sessions()
    tids = [s["thread_id"] for s in sessions]
    assert "real-thread" in tids
    assert "cron" not in tids
    assert "skill:sys_skill" not in tids

    # 模拟历史版本已误建的系统线程会话行 → 启动迁移自愈清理，且不新增
    conn = await db._conn()
    await conn.execute(
        "INSERT INTO sessions(thread_id,title,created_at,updated_at) VALUES('cron','晨报',datetime('now'),datetime('now'))"
    )
    await conn.execute(
        "INSERT INTO sessions(thread_id,title,created_at,updated_at)"
        " VALUES('skill:sys_skill','技能',datetime('now'),datetime('now'))"
    )
    await conn.commit()

    # 读侧立即兜底（不等重启）
    tids = [s["thread_id"] for s in await db.list_sessions()]
    assert "cron" not in tids and "skill:sys_skill" not in tids

    # 启动迁移：误建行被清理；真实线程保持（不重复插入）
    await db._migrate_sessions_from_runs()
    tids = [s["thread_id"] for s in await db.list_sessions()]
    assert tids.count("real-thread") == 1
    assert "cron" not in tids and "skill:sys_skill" not in tids
    rows = await db.fetch_all("SELECT thread_id FROM sessions")
    assert all(r["thread_id"] not in ("cron", "skill:sys_skill") for r in rows)

    # 第三道防线：即便调用方漏传 skip_session，upsert_session 也拒绝系统线程
    await db.upsert_session("skill:sys_skill", "泄漏尝试")
    await db.upsert_session("cron", "泄漏尝试")
    rows = await db.fetch_all("SELECT thread_id FROM sessions")
    assert all(r["thread_id"] not in ("cron", "skill:sys_skill") for r in rows)
