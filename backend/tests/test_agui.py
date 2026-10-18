"""AG-UI 映射层测试（M2.4）。

映射层不是"再写一遍事件"，它的价值在于：内部事件有业务语义（step.phase、
agent_step.summary、final.flags），AG-UI 有严格的配对约束（TextMessage
必须 start/end、step 必须成对）。测试重点是这两件事：
1. 配对约束被满足（否则 AG-UI 客户端会渲染错乱）
2. 业务信息没丢（AG-UI 没有的类型用 CUSTOM 原样透传）
"""

from __future__ import annotations

from app import agui


def _types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def test_run_started_first() -> None:
    """run 必须以 RUN_STARTED 开始，且带 threadId/runId。"""
    m = agui.AgUiMapper("th-1")
    start = m.start()
    assert _types(start) == [agui.RUN_STARTED]
    assert start[0]["threadId"] == "th-1"
    assert start[0]["runId"]


def test_text_stream_is_paired() -> None:
    """text 增量必须包在 TEXT_MESSAGE_START/END 之间（AG-UI 硬约束）。"""
    m = agui.AgUiMapper()
    m.start()
    out1 = m.map({"type": "text", "delta": "本月支出"})
    out2 = m.map({"type": "text", "delta": " 3000 元。"})
    final = m.map({"type": "final", "answer": "本月支出 3000 元。"})

    assert _types(out1) == [agui.TEXT_MESSAGE_START, agui.TEXT_MESSAGE_CONTENT]
    # 第二条增量不应重复 START
    assert _types(out2) == [agui.TEXT_MESSAGE_CONTENT]
    assert out2[0]["delta"] == " 3000 元。"
    # final 前补 END
    assert agui.TEXT_MESSAGE_END in _types(final)
    # 整个流里 START 与 END 各出现一次
    all_types = _types(out1) + _types(out2) + _types(final)
    assert all_types.count(agui.TEXT_MESSAGE_START) == 1
    assert all_types.count(agui.TEXT_MESSAGE_END) == 1


def test_reasoning_and_text_do_not_interleave() -> None:
    """思考流与正文流不能交叉：进正文前必须关掉 reasoning。

    交叉会让客户端把推理内容渲染进回答气泡。
    """
    m = agui.AgUiMapper()
    m.start()
    r = m.map({"type": "thinking", "data": {"content": "先算总额"}})
    assert _types(r) == [agui.REASONING_MESSAGE_START, agui.REASONING_MESSAGE_CONTENT]

    t = m.map({"type": "text", "delta": "答案"})
    assert _types(t) == [
        agui.REASONING_MESSAGE_END,
        agui.TEXT_MESSAGE_START,
        agui.TEXT_MESSAGE_CONTENT,
    ]


def test_step_pairing_and_auto_close() -> None:
    """step 必须成对；内部契约不保证成对时，final 要补发 FINISHED。"""
    m = agui.AgUiMapper()
    m.start()
    s1 = m.map({"type": "step", "id": "market", "label": "查看持仓", "phase": "start"})
    assert _types(s1) == [agui.STEP_STARTED]

    s2 = m.map({"type": "step", "id": "market", "label": "查看持仓", "phase": "done"})
    assert _types(s2) == [agui.STEP_FINISHED]

    # 未闭合的 step：final 时必须补 FINISHED
    m2 = agui.AgUiMapper()
    m2.start()
    m2.map({"type": "step", "id": "ledger", "label": "查账本", "phase": "start"})
    fin = m2.map({"type": "final", "answer": "ok"})
    assert agui.STEP_FINISHED in _types(fin)


def test_agent_step_maps_to_tool_call_triplet() -> None:
    """agent_step → ToolCallStart/Args/End，且参数被序列化成 JSON。"""
    m = agui.AgUiMapper()
    m.start()
    out = m.map(
        {
            "type": "agent_step",
            "name": "get_market_view",
            "args": {"symbol": "600519"},
            "summary": "查持仓",
        }
    )
    types = _types(out)
    assert agui.TOOL_CALL_START in types
    assert agui.TOOL_CALL_ARGS in types
    assert agui.TOOL_CALL_END in types
    args_ev = next(e for e in out if e["type"] == agui.TOOL_CALL_ARGS)
    assert '"symbol"' in args_ev["delta"] and "600519" in args_ev["delta"]
    # toolCallId 三处一致
    ids = {e["toolCallId"] for e in out if "toolCallId" in e}
    assert len(ids) == 1


def test_tool_calls_have_distinct_ids() -> None:
    """多次工具调用不能用同一个 toolCallId，否则客户端会合并成一次。"""
    m = agui.AgUiMapper()
    m.start()
    a = m.map({"type": "agent_step", "name": "get_quote", "args": {"symbol": "600519"}})
    b = m.map({"type": "agent_step", "name": "get_kline", "args": {"symbol": "600519"}})
    id_a = next(e for e in a if e["type"] == agui.TOOL_CALL_START)["toolCallId"]
    id_b = next(e for e in b if e["type"] == agui.TOOL_CALL_START)["toolCallId"]
    assert id_a != id_b


def test_final_carries_business_fields() -> None:
    """final → RUN_FINISHED，业务字段（flags/actions/pending）不能丢。"""
    m = agui.AgUiMapper()
    m.start()
    out = m.map(
        {
            "type": "final",
            "answer": "已记一笔",
            "level": "提示",
            "route": "nl_add",
            "metrics": {"expense": 35},
            "flags": [{"code": "x"}],
            "actions": [{"tab": "ledger"}],
            "pending_token": "tok",
        }
    )
    fin = next(e for e in out if e["type"] == agui.RUN_FINISHED)
    assert fin["result"]["answer"] == "已记一笔"
    assert fin["result"]["route"] == "nl_add"
    assert fin["result"]["flags"] == [{"code": "x"}]
    assert fin["result"]["actions"] == [{"tab": "ledger"}]
    assert fin["result"]["pending_token"] == "tok"


def test_custom_events_preserve_business_payload() -> None:
    """card / plan 这类 AG-UI 没有的类型，用 CUSTOM 原样透传，不丢信息。"""
    m = agui.AgUiMapper()
    m.start()
    card = {"type": "card", "kind": "summary", "data": {"x": 1}}
    out = m.map(card)
    assert _types(out) == [agui.CUSTOM]
    assert out[0]["name"] == "card"
    assert out[0]["value"] == card


def test_error_maps_to_run_error_and_closes_text() -> None:
    """错误也要先闭合文本消息，否则客户端会留下永远 loading 的气泡。"""
    m = agui.AgUiMapper()
    m.start()
    m.map({"type": "text", "delta": "部分回答"})
    err = m.map({"type": "error", "message": "超时"})
    types = _types(err)
    assert agui.TEXT_MESSAGE_END in types
    assert types[-1] == agui.RUN_ERROR
    assert err[-1]["message"] == "超时"


def test_empty_deltas_ignored() -> None:
    """空 delta 不应开出一条空消息（AG-UI 要求 delta 非空）。"""
    m = agui.AgUiMapper()
    m.start()
    assert m.map({"type": "text", "delta": ""}) == []
    assert m.map({"type": "thinking", "data": {}}) == []


async def test_translate_wraps_iterator() -> None:
    """translate() 负责发 RUN_STARTED 并逐条翻译，不缓冲整轮。"""

    async def src():
        yield {"type": "text", "delta": "a"}
        yield {"type": "final", "answer": "a"}

    out = [e async for e in agui.translate(src(), "th")]
    assert out[0]["type"] == agui.RUN_STARTED
    assert out[-1]["type"] == agui.RUN_FINISHED
    assert agui.TEXT_MESSAGE_START in _types(out)


def test_done_only_step_gets_synthetic_start() -> None:
    """回归：内部存在"只发 done 不发 start"的 step（如「已入账」「已记住」）。

    AG-UI 要求 STEP_FINISHED 必须与 STEP_STARTED 配对，否则客户端会收到
    孤立的完成事件（实测在真实 /api/ask/agui 流里出现过）。
    """
    m = agui.AgUiMapper()
    m.start()
    out = m.map({"type": "step", "id": "saved", "label": "已入账", "phase": "done"})
    assert _types(out) == [agui.STEP_STARTED, agui.STEP_FINISHED]
    assert out[0]["stepName"] == out[1]["stepName"] == "已入账"
