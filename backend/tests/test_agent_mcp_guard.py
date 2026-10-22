"""MCP 工具白名单回归：模型不得通过 mcp__ 前缀触达写操作。

背景：本地写工具（记账/买卖/记忆/设置/备份）由确定性前置分支拦截，
READ_TOOLS 明确排除。但外部 MCP 服务器可能暴露同义能力，调用路径
（resolve_mcp_tool → call_mcp_tool）此前不受 WRITE_EXCLUDED 约束。
"""

from __future__ import annotations

import pytest
from app import agent


@pytest.mark.parametrize(
    "name",
    [
        "mcp__record_transaction",
        "mcp__sell_position",
        "mcp__save_user_memory",
        "mcp__set_setting",
        "mcp__backup_now",
        "mcp__record_position",
        "mcp__trigger_morning_report",
    ],
)
def test_mcp_write_tools_are_blocked(name: str) -> None:
    bare = name.removeprefix("mcp__")
    assert bare in agent.WRITE_EXCLUDED, f"{bare} 应在写工具禁止清单里"


def test_mcp_read_tools_not_blocked() -> None:
    """读类 MCP 工具不受影响（避免误伤外部行情/检索服务器）。"""
    for name in ("mcp__get_market_view", "mcp__search_symbol", "mcp__some_external_readonly"):
        bare = name.removeprefix("mcp__")
        assert bare not in agent.WRITE_EXCLUDED


def test_write_tools_absent_from_model_schema() -> None:
    """写工具不得出现在模型可见的 schema 里。"""
    names = {t["function"]["name"] for t in agent.READ_TOOLS}
    assert names.isdisjoint(agent.WRITE_EXCLUDED)
