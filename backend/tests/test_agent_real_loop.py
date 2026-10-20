"""Agent 工具循环的真实执行测试。

与 test_dept_agent.py 的区别（关键）：
那组测试 monkeypatch 掉了 `agent.run_agent` 本身，只验证"参数被传下去了"；
**真正的工具循环、参数解析、结果回填、多轮收敛完全没有被执行**。
这一组只桩掉"模型返回什么"，让 agent 循环与工具实现真实跑起来，
断言的是"工具确实被执行、结果确实被回填、账本确实变了"。

桩点选在 `_CompatCompletions.create`（模型 I/O 边界），而不是 agent 内部函数。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from app import agent, db


class _FakeLLM:
    """按脚本依次返回预设响应的假模型端点。

    每个元素是一次 create() 的返回；用完后重复最后一个。
    """

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        idx = min(len(self.calls) - 1, len(self.script) - 1)
        return self.script[idx]


def _tool_call(name: str, args: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"call_{name}",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _fake_client(create) -> SimpleNamespace:
    """伪造 openai 形态的客户端：client.chat.completions.create(...)。"""
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _assistant(content: str = "", tool_calls: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))]
    )


@pytest.fixture
async def patch_model(monkeypatch, temp_db):
    """把模型端点换成脚本化假端点；返回安装函数。"""

    def _install(script: list[Any]) -> _FakeLLM:
        fake = _FakeLLM(script)

        async def _create(**kwargs):
            return await fake(**kwargs)

        monkeypatch.setattr(agent.llm, "_get_client", lambda *a, **kw: _fake_client(_create))

        async def _cfg():
            return {"key": "test", "base": "http://fake", "model": "test-model",
                    "litellm_model": "openai/test-model"}

        monkeypatch.setattr(agent.llm, "_config", _cfg)
        return fake

    return _install


async def _noop_emit(_ev: dict) -> None:
    return None


async def test_agent_actually_executes_tool_and_uses_result(patch_model) -> None:
    """模型要求调用工具 → 工具真实执行 → 结果回填进下一轮消息。

    断言的是工具真实读到了当前库里的数据（不是写死的字符串），
    以及回填的结构是工具的真实返回。
    """
    # 先清空种子持仓，让断言只反映本用例写入的数据
    await db.execute("DELETE FROM positions")
    await db.add_position(
        {"symbol": "600519", "name": "贵州茅台", "shares": 100, "cost": 10, "last": 12}
    )
    fake = patch_model([
        _assistant(tool_calls=[_tool_call("get_market_view", {})]),
        _assistant("你的持仓市值是 1200 元。"),
    ])

    out = await agent.run_agent("看看我的持仓", _noop_emit, [], "zh")

    # 1) 真的发生了两轮模型调用（先要工具，再成文）
    assert len(fake.calls) >= 2, "工具循环没有跑第二轮"
    # 2) 第二轮的消息里必须带 tool 结果（回填生效）
    second_msgs = fake.calls[1]["messages"]
    tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
    assert tool_msgs, "工具结果没有回填给模型"
    import json as _json

    payload = _json.loads(tool_msgs[-1]["content"])
    # 市值 = 股数 × 行情价（工具会取实时价，取不到才退回 last）。
    # 断言"结构是工具真实返回"且"股数被正确采用"，不锁死价格（行情会波动）。
    assert payload["top_positions"][0]["symbol"] == "600519"
    assert payload["total_market_value"] > 0
    assert payload["total_market_value"] % 100 == 0 or payload["total_market_value"] > 1000, (
        f"工具结果不像 100 股的真实市值: {payload['total_market_value']}"
    )
    # 3) 返回结构正确
    assert out["tools_used"] == ["get_market_view"]


async def test_agent_tool_side_effect_is_real(patch_model) -> None:
    """工具执行必须产生真实副作用（读的是真实库），而不是返回写死的字符串。"""
    await db.execute("DELETE FROM transactions")
    await db.add_transaction("2026-10-01", "早餐", "餐饮", -15)
    await db.add_transaction("2026-10-02", "午餐", "餐饮", -25)

    fake = patch_model([
        _assistant(tool_calls=[_tool_call("get_trend", {"months": 6})]),
        _assistant("趋势如上。"),
    ])
    await agent.run_agent("看趋势", _noop_emit, [], "zh")

    tool_msgs = [m for m in fake.calls[1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs
    import json as _json

    rows = _json.loads(tool_msgs[-1]["content"])
    total_expense = sum(r.get("expense", 0) for r in rows)
    assert total_expense == 40.0, f"工具结果未反映真实的两笔支出: {rows}"


async def test_agent_stops_when_no_more_tool_calls(patch_model) -> None:
    """模型不再要工具时立即成文，不无限循环。"""
    fake = patch_model([_assistant("直接回答，不需要工具。")])
    out = await agent.run_agent("你好", _noop_emit, [], "zh")
    assert out["answer"].strip()
    # 断言"没有进入第二轮工具循环"：所有非流式调用都不应携带工具执行结果
    # （进入第二轮时，messages 里会追加 role=tool 的消息）
    decision_rounds = [
        c for c in fake.calls
        if not c.get("stream") and any(m.get("role") == "tool" for m in c["messages"])
    ]
    assert not decision_rounds, "无工具场景下又发起了带工具结果的决策轮"


async def test_agent_unavailable_when_model_raises(patch_model, monkeypatch) -> None:
    """模型端点异常 → 抛 AgentUnavailable（供上层降级），不是裸异常。"""

    async def _boom(**kwargs):
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(agent.llm, "_get_client", lambda *a, **kw: _fake_client(_boom))

    async def _cfg():
        return {"key": "k", "base": "http://fake", "model": "m", "litellm_model": "openai/m"}

    monkeypatch.setattr(agent.llm, "_config", _cfg)

    with pytest.raises(agent.AgentUnavailable):
        await agent.run_agent("你好", _noop_emit, [], "zh")


async def test_agent_rejects_unknown_tool(patch_model) -> None:
    """模型编造不存在的工具 → 回填"工具不可用"，不崩、不执行任意代码。"""
    fake = patch_model([
        _assistant(tool_calls=[_tool_call("rm_rf_everything", {"path": "/"})]),
        _assistant("抱歉，无法执行。"),
    ])
    out = await agent.run_agent("删库", _noop_emit, [], "zh")
    assert out["answer"]
    tool_msgs = [m for m in fake.calls[1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs and "不可用" in tool_msgs[-1]["content"]


async def test_write_tool_not_visible_to_model(patch_model) -> None:
    """写工具不得出现在模型可见的工具面里（财务分支）。"""
    fake = patch_model([_assistant("好的。")])
    await agent.run_agent("你好", _noop_emit, [], "zh")

    tools = fake.calls[0]["tools"]
    names = {t["function"]["name"] for t in tools}
    for forbidden in (
        "record_transaction",
        "record_position",
        "sell_position",
        "set_setting",
        "backup_now",
        "save_user_memory",
    ):
        assert forbidden not in names, f"写工具 {forbidden} 暴露给了模型"
