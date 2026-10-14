"""Agent 编排层：LLM function calling 多轮工具循环（真正的垂直 agent）。

与 agent_graph.py 的分工：
  - agent_graph.py 负责「编排」：意图分类、节点顺序、条件分支（LangGraph 状态机）；
  - 本模块负责「成文执行」：finalize 节点在 agent 模式下调用本模块的 run_agent，
    让模型自主决定调用 tools.py 里的工具取数并成文；
  - 模型不可用/工具循环失败 → 抛 AgentUnavailable，由 agent_graph.finalize 图内降级
    确定性模板成文（不是双实现，是编排层与执行层的分工）。

技能包装配（先 Agent、后财务）：
  - 财务分支（finalize）：run_agent 默认走财务技能包（AGENT_SYSTEM + READ_TOOLS，
    读类财务工具 + 长期记忆注入）。
  - 通用分支（service._run_general）：run_agent 走通用技能包（GENERAL_SYSTEM +
    GENERAL_TOOLS = web_search / get_now），领域无关，不注入财务数据。

事件契约（新增）：
  {"type":"agent_step","name":"get_market_view","args":{...},"summary":"总市值 282,540 元…"}

隐私边界与确定性内核保持一致：
  - 工具只读本地数据，结果摘要化后回填（truncate_tool_result）
  - 通用闲聊不带任何财务数据出机（路由仍由 service 层决定）
"""

from __future__ import annotations

import json
import pathlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

from . import db, llm, mcp_client, tools

# 写类工具已被确定性分支覆盖（记账/记忆/买卖/设置/备份/晨报都有前置 action/record/memory
# 节点拦截），agent 模式只暴露读类 + 自选维护工具，防止模型在追问/分析语境里越权落库。
WRITE_EXCLUDED = {
    "record_transaction", "save_user_memory", "record_position", "sell_position",
    "set_setting", "backup_now", "trigger_morning_report",
}
READ_TOOLS = [t for t in tools.TOOLS if t["function"]["name"] not in WRITE_EXCLUDED]
# 执行层白名单：只允许模型实际调用「读类 + 自选维护」工具。写工具（记账/记忆/买卖/设置/
# 备份/晨报）由确定性前置分支拦截，绝不暴露给模型执行，防止 prompt 注入/幻觉越权落库。
ALLOWED_IMPL = {
    n: tools.TOOL_IMPL[n]
    for n in {t["function"]["name"] for t in READ_TOOLS}
    if n in tools.TOOL_IMPL
}

# 通用技能包：领域无关工具（时间 / 联网搜索），供 general（非财务）分支装配。
# 这是「先 Agent 后财务」的落点：通用 Agent 内核不依赖任何财务能力。
GENERAL_TOOLS: list[dict[str, Any]] = tools.GENERAL_TOOLS
GENERAL_IMPL: dict[str, Any] = tools.GENERAL_IMPL

# 通用 Agent 内核说明书（general 分支用）：领域无关的自主 agent 行为规则。
GENERAL_SYSTEM = (
    "You are an autonomous general-purpose agent. Rules:\n"
    "1. Need a real fact, date, time, or the latest news? Call a tool to fetch it — never invent it.\n"
    "2. You may call several independent tools in one turn and continue after their results return.\n"
    "3. Give a one-line conclusion first, then the key points, in the user's language.\n"
    "4. If a tool fails or returns nothing, say so plainly rather than guessing.\n"
    "You have only general-purpose tools (web_search, get_now) and NO access to the user's financial "
    "data — for portfolio/ledger/finance questions say you don't have that data."
)

Emit = Callable[[dict[str, Any]], Awaitable[None]]

MAX_TURNS = 5

_AGENTS_DIR = pathlib.Path(__file__).parent / "agents"

def _load_instructions(agent_name: str) -> str:
    """从 agents/<name>/instructions.md 读系统提示词。"""
    p = _AGENTS_DIR / agent_name / "instructions.md"
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip()

AGENT_SYSTEM = _load_instructions("supervisor")


class AgentUnavailable(Exception):
    """模型未配置或工具循环失败：调用方应降级到确定性路径。"""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _tool_summary(name: str, result_text: str) -> str:
    """给前端的工具结果摘要（简短、可读）。"""
    try:
        data = json.loads(result_text)
    except Exception:  # noqa: BLE001
        return result_text[:80]
    if name == "get_market_view":
        if not isinstance(data, dict):
            return result_text[:80]
        return f"总市值 {data.get('total_market_value', 0):,} 元，累计盈亏 {data.get('total_pnl', 0):,} 元"
    if name == "get_ledger_view":
        if not isinstance(data, dict):
            return result_text[:80]
        return f"{data.get('month', '')} 收入 {data.get('income', 0):,}、支出 {data.get('expense', 0):,}、结余 {data.get('net', 0):,}"
    if name == "get_risk_flags":
        if not isinstance(data, dict):
            return result_text[:80]
        return f"发现 {data.get('count', 0)} 项需关注"
    if name == "get_budget":
        if not isinstance(data, dict):
            return result_text[:80]
        return f"{data.get('month', '')} 支出 {data.get('total_spent', 0):,} / 预算 {data.get('total_budget', 0):,}"
    if name == "get_trend":
        n = len(data) if isinstance(data, list) else 0
        return f"已取近 {n} 个月趋势"
    if name == "record_transaction":
        if not isinstance(data, dict):
            return result_text[:80]
        return f"已入账：{data.get('item', '')} {data.get('amount', 0):,} 元（{data.get('category', '')}）"
    if name == "get_kline":
        if not isinstance(data, dict):
            return result_text[:80]
        n = len(data.get("points", [])) if isinstance(data, dict) else 0
        return f"已取 {data.get('symbol', '')} {n} 个K线点"
    if name == "get_goals":
        if isinstance(data, dict) and data.get("empty"):
            return "暂无财务目标"
        if isinstance(data, list):
            parts = [f"{g.get('name', '')} {g.get('pct', 0)}%" for g in data[:3]]
            return "目标进度：" + "、".join(parts)
        return result_text[:80]
    if name == "get_user_memory":
        if isinstance(data, dict) and data.get("empty"):
            return "暂无长期记忆"
        if isinstance(data, list):
            return f"共 {len(data)} 条记忆"
        return result_text[:80]
    if name == "save_user_memory":
        return "已记住" if data.get("ok") else "记忆未保存"
    if name == "get_health_check":
        return f"体检综合评分 {data.get('score', 0)} 分，{data.get('summary', '')}"
    return result_text[:80]


async def _stream_final_answer(
    client: Any,
    cfg: dict[str, Any],
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    emit: Emit,
) -> str:
    """流式生成最终回答。返回完整文本；失败时退回非流式兜底。"""
    full_parts: list[str] = []
    try:
        stream = await client.chat.completions.create(
            model=cfg["model"] or "gpt-4o-mini",
            messages=messages,
            tools=tool_schemas,
            tool_choice="auto",
            temperature=0.2,
            stream=True,
            timeout=120.0,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                full_parts.append(delta)
                # 逐 token 流式推送前端
                await emit({
                    "type": "token",
                    "data": {"content": delta},
                    "node": "finalize",
                })
    except Exception:
        # 流式失败时退回非流式兜底
        try:
            resp = await client.chat.completions.create(
                model=cfg["model"] or "gpt-4o-mini",
                messages=messages,
                tools=tool_schemas,
                tool_choice="auto",
                temperature=0.2,
                stream=False,
            )
            content = (resp.choices[0].message.content or "").strip()
            if content:
                # 一次性推出去（没有逐 token 的流式，但内容完整）
                await emit({
                    "type": "token",
                    "data": {"content": content},
                    "node": "finalize",
                })
                return content
        except Exception as exc:
            raise AgentUnavailable(f"模型最终成文失败：{type(exc).__name__}") from exc
        return ""

    return "".join(full_parts).strip()


async def _compress_history(messages: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """长会话上下文压缩（progressive disclosure）。

    当 messages 超过 8 条（含 system+user+assistant+tool），把除最近 4 条外
    的早期历史用一句话摘要替代，防 context window 溢出。
    摘要由 LiteLLM 廉价模型（如 gpt-4o-mini）快速产出。
    """
    if len(messages) <= 8:
        return messages
    # 保底逻辑：保留 system 消息 + 最近 4 轮对话，把中间部分压缩
    # 找到 system 消息数量
    system_count = sum(1 for m in messages if m.get("role") == "system")
    keep_tail = 4  # 保留最近 4 条对话（含 tool 消息）
    if len(messages) - system_count <= keep_tail + 1:
        return messages
    head = messages[: system_count + 1]  # system + 首个 user
    tail = messages[-keep_tail:]  # 最近 4 条
    middle = messages[system_count + 1 : -keep_tail]

    if not middle:
        return messages

    # 用简短提示请模型摘要早期对话
    middle_text = "\n".join(
        f"[{m.get('role', '?')}] {str(m.get('content', ''))[:200]}"
        for m in middle
    )[:2000]

    try:
        summary = await llm.stream_text_short(
            f"把下面多轮对话压缩为一句话摘要（保留关键数据和意图，≤80字）：\n{middle_text}",
            timeout=15.0,
        )
    except Exception:
        summary = None

    if not summary:
        return messages  # 压缩失败不丢数据，原样返回

    compressed = {
        "role": "system",
        "content": f"（前面对话摘要：{summary}）以下是最后的对话：",
    }
    return [*head, compressed, *tail]


async def run_agent(
    question: str,
    emit: Emit,
    history: list[dict[str, str]] | None = None,
    lang: str = "zh",
    *,
    system: str | None = None,
    tools_list: list | None = None,
    impl_map: dict | None = None,
    inject_memories: bool = True,
) -> dict[str, Any]:
    """跑一轮 agent：模型自主调用工具后成文。失败抛 AgentUnavailable。

    默认走财务技能包（AGENT_SYSTEM + READ_TOOLS + 长期记忆注入）；
    general 分支通过 system/tools_list/impl_map/inject_memories 装配通用技能包。
    """
    cfg = await llm._config()  # noqa: SLF001 — 同一包内复用配置读取
    if cfg is None:
        raise AgentUnavailable("未接入模型")

    client = llm._get_client(cfg, timeout=60.0)  # noqa: SLF001 — LiteLLM 后端
    # Agent 行为可配置化：工具轮次上限与失败反思重试由设置中心控制（默认与历史一致）。
    _s = await db.get_settings()
    turn_cap = max(1, min(int((_s.get("agent_tool_turns") or MAX_TURNS) or MAX_TURNS), 30))
    reflect = (_s.get("agent_reflect") or "on") != "off"
    system_prompt = system if system is not None else AGENT_SYSTEM
    lang_rule = "请用简体中文回答用户的问题。" if lang == "zh" else "Answer the user in English."
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": lang_rule},
    ]
    if history:
        messages.append(
            {
                "role": "system",
                "content": "同一会话历史（仅作上下文参考，数字一律以工具结果为准）："
                + json.dumps(history, ensure_ascii=False)[:2000],
            }
        )
    # 长期记忆预注入（用户主动要求记住的）：模型无需先调工具即可参考用户背景。
    # 仅财务分支注入（inject_memories=True）；通用 agent 分支不注入，隐私边界不变。
    memories = await db.list_memory() if inject_memories else []
    if memories:
        mem_text = "\n".join(f"- {m['content']}" for m in memories[:5])
        messages.append(
            {
                "role": "system",
                "content": "用户长期记忆（用户主动要求记住的，作上下文参考，需要精确数字仍以工具结果为准）：\n"
                + mem_text[:400],
            }
        )
    messages.append({"role": "user", "content": question})

    steps: list[dict[str, Any]] = []
    used_tools: list[str] = []
    tool_counts: dict[str, int] = {}

    # 长会话上下文压缩：messages 超过 8 条时，用 stream_text_short 把早期历史摘要化
    # （对齐 Claude Code 的 progressive disclosure：长会话摘要兜底，防 context window 溢出）
    messages = await _compress_history(messages, cfg)

    tool_schemas = tools_list if tools_list is not None else READ_TOOLS
    tool_map = impl_map if impl_map is not None else ALLOWED_IMPL
    # P2 MCP：把已配置 MCP 服务器提供的工具动态合并进工具列表（仅财务分支，通用分支不接外部工具）
    mcp_schemas: list[dict[str, Any]] = []
    if tools_list is None:
        try:
            mcp_schemas = await mcp_client.refresh()
            tool_schemas = READ_TOOLS + mcp_schemas
        except Exception:  # noqa: BLE001 — MCP 异常不影响主流程
            pass
    for _turn in range(turn_cap):
        try:
            resp = await client.chat.completions.create(
                model=cfg["model"] or "gpt-4o-mini",  # model 可留空 → 用默认，与 stream_narrate 一致
                messages=messages,
                tools=tool_schemas,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001 — 端点失败/不支持 tools → 降级
            raise AgentUnavailable(f"模型调用失败：{type(exc).__name__}") from exc

        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            # 最终回答：流式输出（逐 token 推送到前端 markdown 渲染）
            # 先尝试流式；失败时退回非流式兜底
            full_answer = await _stream_final_answer(
                client, cfg, messages, tool_schemas, emit
            )
            if not full_answer:
                raise AgentUnavailable("模型未产出回答")
            return {
                "answer": full_answer,
                "steps": steps,
                "tools_used": used_tools,
                "tool_counts": tool_counts,
                "llm": "llm",
            }

        # 模型要求调用工具：先原样回填 assistant 消息，再执行工具并回填结果。
        # 若模型在调用工具的同时给出说明（如"我来查一下"），作为 thinking 过程展示。
        if (msg.content or "").strip():
            await emit({
                "type": "thinking",
                "data": {"content": (msg.content or "").strip()},
                "node": "finalize",
            })
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            name = tc.function.name
            # P2 MCP：外部 MCP 工具（server 名一致时才走 MCP 调用）
            mcp_hit = mcp_client.resolve_mcp_tool(name) if mcp_schemas else None
            impl = tool_map.get(name)
            if impl is None and mcp_hit is None:
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": f"工具不可用：{name}"}
                )
                continue
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            tool_counts[name] = tool_counts.get(name, 0) + 1
            used_tools.append(name)
            # 工具生命周期：running → 结果
            await emit({
                "type": "tool",
                "data": {
                    "id": tc.id, "name": name, "args": args,
                    "status": "running", "node": "finalize", "ts": _now_ms(),
                },
            })
            started = time.monotonic()
            try:
                if mcp_hit is not None:
                    # MCP 工具调用（外部服务器）
                    result = await mcp_client.call_mcp_tool(mcp_hit[0], mcp_hit[1], args)
                else:
                    result = tools.truncate_tool_result(await impl(args))
                status = "done"
            except Exception as exc:  # noqa: BLE001 — 工具失败回填错误，不让循环崩
                result = f"工具执行失败：{type(exc).__name__}: {exc}"
                status = "error"
                # P1 经验库：把失败「踩坑点」记入 reflections，供下次反思参考（异步不阻塞）
                try:
                    await db.add_reflection(
                        name,
                        args,
                        str(exc)[:200],
                        f"工具 {name} 失败：{type(exc).__name__}。检查参数与调用方式后重试。",
                    )
                except Exception:  # noqa: BLE001 — 记录失败不影响主流程
                    pass
            duration_ms = int((time.monotonic() - started) * 1000)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            # 反思重试（可配置）：工具失败时明确提示模型修正参数/换思路，下一轮自纠（防反复撞同一个错）
            if status == "error" and reflect:
                # 参考经验库里的历史踩坑点，避免重复同一个错误
                lessons = await db.list_reflections(limit=5)
                lesson_txt = ""
                if lessons:
                    lesson_txt = "过往同类踩坑记录：\n" + "\n".join(
                        f"- {ls['tool']}: {ls['lesson']}" for ls in lessons if ls["tool"] == name
                    )
                messages.append({
                    "role": "system",
                    "content": (
                        "上一次工具调用失败了。请反思原因（参数、关键词、流程），修正后重试，"
                        "不要重复同样的错误；若确实无法完成，如实告诉用户。"
                        + (lesson_txt or "")
                    ),
                })
            summary = _tool_summary(name, result)
            steps.append({"name": name, "args": args, "summary": summary})
            await emit({
                "type": "tool",
                "node": "finalize",
                "data": {
                    "id": tc.id, "name": name, "status": status,
                    "summary": summary, "duration_ms": duration_ms, "ts": _now_ms(),
                },
            })
            # 兼容旧契约：agent_step 仍发（summary 聚合）
            await emit({"type": "agent_step", "name": name, "args": args, "summary": summary})

    raise AgentUnavailable(f"工具循环超过 {MAX_TURNS} 轮未收敛")