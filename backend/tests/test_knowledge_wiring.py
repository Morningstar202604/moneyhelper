"""知识库接线：入库的文档必须真的出现在 Agent 的 system 消息里。

只测纯函数（test_knowledge.py）不够——那只能证明检索算法对，
不能证明 run_agent 真的把它注入了。这里拦截 messages 构造过程做断言。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from app import agent, db


class _CapturingCompletions:
    """记录收到的 messages，然后直接给出最终回答（不再调工具）。"""

    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    async def create(self, **kwargs):  # noqa: ANN003
        self.seen.append(kwargs["messages"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="好的", tool_calls=None))]
        )


@pytest.fixture
def env(monkeypatch, temp_db):
    comp = _CapturingCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    monkeypatch.setattr(agent.llm, "_get_client", lambda *a, **k: client)  # noqa: SLF001
    async def fake_config():
        return {"base": "", "key": "", "model": "t", "provider": "openai"}

    monkeypatch.setattr(agent.llm, "_config", fake_config)

    async def fake_stream(*a, **k):  # noqa: ANN002, ANN003
        return "好的"

    monkeypatch.setattr(agent, "_stream_final_answer", fake_stream)
    return comp


async def _seed_doc() -> None:
    att = await db.add_attachment("保单.txt", "text", 100, "重疾险等待期 90 天，保额 50 万。")
    await db.set_attachment_indexed(att["id"], True)


async def test_indexed_doc_injected_into_system_messages(env) -> None:
    await _seed_doc()

    async def emit(_ev):
        pass

    await agent.run_agent("重疾险等待期多久", emit, lang="zh")
    assert env.seen, "应至少调用一次模型"
    joined = json.dumps(env.seen[0], ensure_ascii=False)
    assert "知识库" in joined
    assert "90 天" in joined, "命中的片段原文应出现在 system 消息里"


async def test_non_indexed_doc_not_injected(env) -> None:
    await db.add_attachment("未入库.txt", "text", 50, "这段话不应该被检索到。")

    async def emit(_ev):
        pass

    await agent.run_agent("未入库的内容", emit, lang="zh")
    joined = json.dumps(env.seen[0], ensure_ascii=False)
    assert "不应该被检索到" not in joined


async def test_knowledge_can_be_disabled(env, monkeypatch) -> None:
    await _seed_doc()

    original = db.get_settings

    async def settings_off():
        s = await original()
        s["knowledge_enabled"] = "off"
        return s

    monkeypatch.setattr(db, "get_settings", settings_off)

    async def emit(_ev):
        pass

    await agent.run_agent("重疾险等待期多久", emit, lang="zh")
    joined = json.dumps(env.seen[0], ensure_ascii=False)
    assert "90 天" not in joined
