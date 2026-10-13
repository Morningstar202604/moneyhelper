"""tx_rules 的 settings 表读写：把规则 JSON 序列化后存到 settings 表的 "tx_rules" key。

首次读取（key 不存在）时写入 builtin_rules()。版本号存 "tx_rules_version"。
"""

from __future__ import annotations

import json

from . import db
from .rules import DEFAULT_RULE_VERSION, builtin_rules

TX_RULES_KEY = "tx_rules"
TX_RULES_VERSION_KEY = "tx_rules_version"


async def get_rules() -> list[dict]:
    """读规则列表；settings 表还没有 tx_rules 时写入内置规则。"""
    settings = await db.get_settings()
    raw = settings.get(TX_RULES_KEY)
    if not raw:
        rules = builtin_rules()
        await save_rules(rules)
        return rules
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return builtin_rules()


async def save_rules(rules: list[dict]) -> None:
    """写入规则列表 JSON + 版本号到 settings 表。"""
    await db.set_setting(TX_RULES_KEY, json.dumps(rules, ensure_ascii=False))
    await db.set_setting(TX_RULES_VERSION_KEY, str(DEFAULT_RULE_VERSION))


async def reset_to_builtin() -> list[dict]:
    """清空并回退到内置规则。"""
    rules = builtin_rules()
    await save_rules(rules)
    return rules
