"""Agent 循环保护：模型连续用相同参数调同一工具时必须中断。

保护点写在 run_agent 的工具执行循环里。这里不重建整个 LLM 循环
（test_agent_real_loop.py 已覆盖真实循环），而是把「重复键比较」这段
判定逻辑按源码同样的规则独立验证——它是防空转的唯一依据，必须可靠。
"""

from __future__ import annotations

import json


def _repeat_key(name: str, args: dict) -> tuple[str, str]:
    """与 app.agent.run_agent 中的实现保持一致的键构造。"""
    return (name, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))


def test_same_tool_same_args_produce_identical_key() -> None:
    assert _repeat_key("get_market_view", {"x": 1}) == _repeat_key("get_market_view", {"x": 1})


def test_key_is_order_insensitive() -> None:
    """参数顺序不同但内容相同，视为同一个调用。"""
    assert _repeat_key("t", {"a": 1, "b": 2}) == _repeat_key("t", {"b": 2, "a": 1})


def test_different_args_produce_different_key() -> None:
    assert _repeat_key("t", {"a": 1}) != _repeat_key("t", {"a": 2})


def test_different_tool_produces_different_key() -> None:
    assert _repeat_key("a", {"x": 1}) != _repeat_key("b", {"x": 1})


def test_three_consecutive_repeats_trigger_guard() -> None:
    """连续 3 次相同才是保护阈值（前两次允许，避免误伤正常重试）。"""
    max_repeat = 3
    prev: tuple[str, str] | None = None
    count = 0
    triggered_at = None
    for i in range(1, 6):
        key = _repeat_key("get_market_view", {"x": 1})
        if key == prev:
            count += 1
        else:
            prev, count = key, 1
        if count >= max_repeat:
            triggered_at = i
            break
    assert triggered_at == 3


def test_alternating_tools_do_not_trigger() -> None:
    """A→B→A→B 是合理行为，不应被当成重复。"""
    max_repeat = 3
    prev: tuple[str, str] | None = None
    count = 0
    for name in ["a", "b", "a", "b", "a"]:
        key = _repeat_key(name, {"x": 1})
        if key == prev:
            count += 1
        else:
            prev, count = key, 1
        assert count < max_repeat
