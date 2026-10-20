"""技能开关的运行时落点：设置 → Agent 的技能真正生效（而非只存配置）。

覆盖：
- 内置技能关闭 → 对应 agent 工具从工具面移除
- 「长期记忆」关闭 → 「记住…」明确回执且不写入；开启 → 正常写入
- 自定义技能（AI 生成）启用 → 注入 agent 个性化指令块；关闭/内置技能不进注入
"""

from __future__ import annotations

import json

from app import agent, agent_config, db


async def _set_skill(temp_db, skill_id: str, enabled: bool, *, name: str = "", desc: str = "") -> None:
    cfg = await agent_config.get_config()
    skills = cfg.setdefault("skills", {})
    entry = skills.setdefault(skill_id, {"name": name or skill_id, "description": desc})
    entry["enabled"] = enabled
    await db.set_setting("agent_config", json.dumps(cfg, ensure_ascii=False))


async def _supervisor_tool_names() -> set[str]:
    """按 agent.run_agent 的实际装配规则算出工具名集合。"""
    names = {t["function"]["name"] for t in agent.READ_TOOLS}
    names -= await agent_config.disabled_tool_names()
    return names


async def test_disabled_builtin_skill_removes_tools(temp_db) -> None:
    """关闭「风险体检」→ 工具面不再有 get_risk_flags / get_health_check。"""
    names_before = await _supervisor_tool_names()
    assert {"get_risk_flags", "get_health_check"} <= names_before

    await _set_skill(temp_db, "risk_analysis", False)
    names_after = await _supervisor_tool_names()
    assert "get_risk_flags" not in names_after
    assert "get_health_check" not in names_after
    # 其他只读工具不受影响（开关粒度正确）
    assert "get_market_view" in names_after


async def test_disabled_goals_skill_removes_tool(temp_db) -> None:
    await _set_skill(temp_db, "goals_tracking", False)
    names = await _supervisor_tool_names()
    assert "get_goals" not in names


async def test_long_memory_disabled_receipt_and_no_write(temp_db) -> None:
    """「长期记忆」关闭时：「记住…」明确回执、不写入 user_memory 表。"""
    from app import service

    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    # 关闭技能
    await _set_skill(temp_db, "long_memory", False)
    out = await service._try_save_memory("记住我每个月 10 号要还房贷", emit, "zh")
    assert out is not None
    assert out["route"] == "memory"
    assert "关闭" in out["answer"]
    assert await db.list_memory() == []  # 未写入
    assert events == []  # 没有「已记住」步骤事件

    # 打开技能 → 正常写入
    await _set_skill(temp_db, "long_memory", True)
    out2 = await service._try_save_memory("记住我每个月 10 号要还房贷", emit, "zh")
    assert out2 is not None and "好，我记住了" in out2["answer"]
    items = await db.list_memory()
    assert items and "房贷" in items[0]["content"]


async def test_custom_skill_prompt_injection(temp_db) -> None:
    """自定义技能（AI 生成）启用 → 注入指令块；关闭/内置技能不注入。"""
    await _set_skill(temp_db, "dca_reminder", True, name="定投提醒助手", desc="每周日晚提醒检查定投计划")
    prompt = await agent_config.custom_skill_prompt()
    assert "定投提醒助手" in prompt and "每周日晚" in prompt
    # 内置技能不该出现在自定义注入里（它们由工具/调度器等运行时消费）
    assert "风险体检" not in prompt

    await _set_skill(temp_db, "dca_reminder", False)
    assert await agent_config.custom_skill_prompt() == ""


async def test_disabled_tool_names_mapping(temp_db) -> None:
    """disabled_tool_names 只反映被关闭的内置技能。"""
    assert await agent_config.disabled_tool_names() == set()
    await _set_skill(temp_db, "goals_tracking", False)
    names = await agent_config.disabled_tool_names()
    assert "get_goals" in names
    # 定制技能（非内置）不影响工具（它走 prompt 注入）
    await _set_skill(temp_db, "my_custom", False)
    assert "get_goals" in (await agent_config.disabled_tool_names())
