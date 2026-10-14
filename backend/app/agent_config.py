"""Agent 配置系统：角色 / skills / 工具开关。

默认配置在 agents/default_config.json，启动时写入 settings 表。
用户可以在设置页自定义修改。
"""

from __future__ import annotations

import json
import pathlib
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
