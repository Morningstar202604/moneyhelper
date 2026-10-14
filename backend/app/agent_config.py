"""Agent 配置系统：角色 / skills / 工具开关。

默认配置在 agents/default_config.json，启动时写入 settings 表。
用户可以在设置页自定义修改。
"""

from __future__ import annotations

import json
import pathlib
import re
import uuid
from typing import Any

from . import db
from .logging_utils import get_logger

log = get_logger(__name__)

_CONFIG_FILE = pathlib.Path(__file__).parent / "agents" / "default_config.json"
_SETTINGS_KEY = "agent_config"


def _load_default() -> dict[str, Any]:
    """从 default_config.json 读默认配置。"""
    if not _CONFIG_FILE.exists():
        return {}
    return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))


async def init_default_config() -> None:
    """启动时调用：如果 settings 表里没有 agent_config，就写入默认值。"""
    existing = (await db.get_settings()).get(_SETTINGS_KEY)
    if existing:
        log.info("agent.config.loaded from_db=true")
        return
    default = _load_default()
    if not default:
        return
    await db.set_setting(_SETTINGS_KEY, json.dumps(default, ensure_ascii=False))
    log.info("agent.config.init_default version=%s", default.get("version", "?"))


async def get_config() -> dict[str, Any]:
    """读当前 agent 配置（数据库里的，没有就用默认）。"""
    raw = (await db.get_settings()).get(_SETTINGS_KEY)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return _load_default()


async def update_config(new_config: dict[str, Any]) -> None:
    """保存用户修改后的配置。"""
    await db.set_setting(_SETTINGS_KEY, json.dumps(new_config, ensure_ascii=False))
    log.info("agent.config.updated")


async def get_agent_tools(agent_name: str) -> list[str] | str:
    """获取某个 agent 启用的工具列表。返回 'all' 表示全部工具。"""
    cfg = await get_config()
    agent_cfg = cfg.get("agents", {}).get(agent_name, {})
    return agent_cfg.get("tools", "all")


async def is_skill_enabled(skill_name: str) -> bool:
    """检查某个 skill 是否启用。"""
    cfg = await get_config()
    skill_cfg = cfg.get("skills", {}).get(skill_name, {})
    return skill_cfg.get("enabled", True)


# 内置技能（default_config.json 预置）；其余为用户/AI 生成的「自定义技能」。
BUILTIN_SKILLS = frozenset(
    {"risk_analysis", "goals_tracking", "morning_report", "long_memory"}
)

# 内置技能 → 运行时能力映射（技能开关真正生效的落点）：
# 关闭某技能 → 对应工具从 agent 工具面移除（agent / react 两条路径都过滤）。
_SKILL_TOOLS: dict[str, set[str]] = {
    "risk_analysis": {"get_risk_flags", "get_health_check"},
    "goals_tracking": {"get_goals"},
    "long_memory": {"get_user_memory"},
}


async def disabled_tool_names() -> set[str]:
    """按已关闭的内置技能，返回应从 agent 工具面移除的工具名集合。"""
    cfg = await get_config()
    skills = cfg.get("skills", {})
    out: set[str] = set()
    for skill, tool_names in _SKILL_TOOLS.items():
        if not skills.get(skill, {}).get("enabled", True):
            out |= tool_names
    return out


async def custom_skill_prompt() -> str:
    """启用中的「自定义技能」（非内置）→ 注入 agent 的个性化指令块。

    这一块让「设置 → Agent → AI 生成技能」真正生效：生成的技能以
    「名称：描述」形式进入系统提示，模型会在相关场景遵循。
    """
    cfg = await get_config()
    lines: list[str] = []
    for sid, s in (cfg.get("skills") or {}).items():
        if sid in BUILTIN_SKILLS or not s.get("enabled", True):
            continue
        name = str(s.get("name") or sid).strip()
        desc = str(s.get("description") or "").strip()
        if name:
            lines.append(f"- {name}：{desc}" if desc else f"- {name}")
    if not lines:
        return ""
    return "用户自定义技能（用户主动启用，请在相关场景遵循）：\n" + "\n".join(lines[:10])


async def generate_suggestion(kind: str, prompt: str, agent_name: str = "") -> dict[str, Any] | None:
    """按自然语言描述生成配置建议（skill 或某 agent 的名称/描述）。

    只产出建议、不落库——由用户在设置页确认后随既有保存流程写入。
    模型不可用 / 输出非法一律返回 None（fail-closed，调用方给出友好错误）。
    """
    from . import llm

    if kind == "skill":
        system = (
            "你是财务助手的功能技能设计器。根据用户描述生成一个 JSON："
            '{"id": "snake_case_ascii 唯一短 id", "name": "4-6 字中文名", '
            '"description": "一句话说明这个技能做什么（中文，40 字以内）"}。只输出 JSON，不要多余文字。'
        )
    elif kind == "agent":
        system = (
            f"你是财务助手中 {agent_name or '某个'} 角色的设计器。根据用户描述生成 JSON："
            '{"name": "4-8 字中文角色名", "description": "一句话职责说明（中文，40 字以内）"}。只输出 JSON。'
        )
    else:
        return None

    out = await llm.json_complete(system, prompt, timeout=20.0)
    if not isinstance(out, dict):
        return None
    name = str(out.get("name") or "").strip()[:20]
    desc = str(out.get("description") or "").strip()[:80]
    if not name or not desc:
        return None
    if kind == "skill":
        raw_id = str(out.get("id") or "").strip().lower()
        sid = re.sub(r"[^a-z0-9_]+", "_", raw_id).strip("_") or f"skill_{uuid.uuid4().hex[:8]}"
        return {"id": sid, "name": name, "description": desc, "enabled": True}
    return {"name": name, "description": desc}
