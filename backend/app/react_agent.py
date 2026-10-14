"""LangGraph 官方 create_react_agent 替换手写 tool loop。

不重复造轮子：LangGraph 官方的 ReAct agent 已经处理了：
- 工具调用循环
- 错误重试
- 上下文管理
- 多轮对话状态
- 流式输出

我们只做一层薄适配：把 OpenAI function calling 格式的工具包装成 LangChain @tool，
然后调 create_react_agent，结果转成我们的 SSE 事件格式。
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from langchain_litellm import ChatLiteLLM
from langgraph.prebuilt import create_react_agent
from pydantic import Field, create_model

from . import agent, db, llm, tools
from .logging_utils import get_logger

log = get_logger(__name__)


def _make_langchain_tool(name: str, description: str, impl: Any, param_schema: dict | None = None) -> StructuredTool:
    """把 OpenAI 格式工具包装成 LangChain StructuredTool。"""

    async def _run(**kwargs: Any) -> str:
        return await impl(kwargs)

    # 从 OpenAI schema 提取参数名
    params = (param_schema or {}).get("properties", {})
    required = (param_schema or {}).get("required", [])

    # 动态生成 pydantic model
    fields: dict[str, Any] = {}
    for pname, pspec in params.items():
        ptype = str if pspec.get("type") == "string" else (int if pspec.get("type") == "integer" else str)
        default = ... if pname in required else None
        fields[pname] = (ptype, Field(default, description=pspec.get("description", "")))

    ArgsModel = create_model("ToolArgs", **fields)

    return StructuredTool.from_function(
        coroutine=_run,
        name=name,
        description=description,
        args_schema=ArgsModel,
    )


async def _build_finance_tools(agent_name: str = "supervisor") -> list[StructuredTool]:
    """把财务读类工具包装成 LangChain 工具，按 agent 分组过滤。

    每个 agent 只看到自己该用的工具，减少 token 消耗。
    设置页的 agent 配置（设置 → Agent → 工具开关）在此真正生效：
    配置为工具名列表时取交集（写工具始终被 WRITE_EXCLUDED 排除，只读不变量不变）。
    """
    # 按 agent 分组的默认工具名
    AGENT_TOOLS: dict[str, set[str]] = {
        "bookkeeping": {
            "get_ledger_view", "get_budget", "get_trend", "record_transaction",
        },
        "portfolio": {
            "get_market_view", "get_kline", "search_symbol", "get_quote",
            "add_to_watchlist", "remove_from_watchlist", "get_watchlist",
            "record_position", "sell_position",
        },
        "supervisor": {
            # supervisor 用所有工具（总调度）
        },
    }
    allowed = AGENT_TOOLS.get(agent_name, set())
    # 读用户配置（缺行时回落内置默认）；配置为具体列表时与内置分组取交集
    try:
        from . import agent_config

        configured = await agent_config.get_agent_tools(agent_name)
        if isinstance(configured, list):
            allowed = set(configured) if not allowed else (allowed & set(configured))
    except Exception:  # noqa: BLE001 — 配置读取失败回落内置默认
        pass

    lc_tools: list[StructuredTool] = []
    for t in tools.TOOLS:
        fname = t["function"]["name"]
        if fname in agent.WRITE_EXCLUDED:
            continue
        # 按 agent 分组过滤（supervisor 不过滤）
        if allowed and fname not in allowed:
            continue
        impl = tools.TOOL_IMPL.get(fname)
        if not impl:
            continue
        lc_tools.append(_make_langchain_tool(
            name=fname,
            description=t["function"]["description"],
            impl=impl,
            param_schema=t["function"].get("parameters"),
        ))
    return lc_tools


async def run_react_agent(question: str, system_prompt: str, lang: str = "zh", agent_name: str = "supervisor") -> dict[str, Any]:
    """用 LangGraph 官方 create_react_agent 跑一轮 agent。

    返回与 agent.run_agent 兼容的格式：{answer, steps, tools_used, llm}
    """
    cfg = await llm._config()
    if cfg is None:
        raise RuntimeError("未接入模型")

    # 用 ChatLiteLLM 作为 LangChain chat model
    # request_timeout 与 llm.py 约定的 60s 一致：模型端点挂起时不无限拖住整轮问答
    llm_model = ChatLiteLLM(
        model=cfg["litellm_model"],
        api_base=cfg.get("base"),
        api_key=cfg.get("key"),
        temperature=0.2,
        max_tokens=2048,
        request_timeout=60,
    )

    lc_tools = await _build_finance_tools(agent_name)

    # 长期记忆注入
    memories = await db.list_memory()
    mem_text = ""
    if memories:
        mem_text = "\n用户长期记忆（用户主动要求记住的）：\n" + "\n".join(f"- {m['content']}" for m in memories[:5])

    lang_rule = "请用简体中文回答用户的问题。" if lang == "zh" else "Answer in English."
    full_system = f"{system_prompt}\n{lang_rule}{mem_text}"

    # 创建 ReAct agent
    agent_app = create_react_agent(
        model=llm_model,
        tools=lc_tools,
        prompt=full_system,
    )

    # 跑 agent
    result = await agent_app.ainvoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": "default"}},
    )

    # 提取结果
    messages = result.get("messages", [])
    final_answer = ""
    steps: list[dict[str, Any]] = []
    tools_used: list[str] = []

    for msg in messages:
        msg_type = getattr(msg, "type", "")
        if msg_type == "ai":
            tc = getattr(msg, "tool_calls", None)
            if tc:
                for t in tc:
                    steps.append({"name": t.get("name", ""), "summary": ""})
                    tools_used.append(t.get("name", ""))
            elif getattr(msg, "content", ""):
                final_answer = msg.content
        elif msg_type == "tool":
            # 工具结果回填到最后一个 step
            if steps:
                steps[-1]["summary"] = str(getattr(msg, "content", ""))[:200]

    return {
        "answer": final_answer,
        "steps": steps,
        "tools_used": tools_used,
        "tool_counts": {},
        "llm": "react",
    }
