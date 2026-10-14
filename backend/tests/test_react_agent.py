"""react_agent 工具装配回归测试。

锁定两个曾导致 LangGraph react 路径每次静默降级的缺陷：
- `_build_finance_tools` 曾引用未导入的 `agent.WRITE_EXCLUDED`（NameError，每次请求降级手写 loop）
- `_make_langchain_tool` 曾用 `type()` 直接建 pydantic 模型（pydantic 2 报
  "A non-annotated attribute was detected"，工具装配必失败）
"""

from __future__ import annotations

import json

from app import agent, agent_config, db, react_agent


async def test_build_finance_tools_supervisor_gets_readonly_tools(temp_db) -> None:
    """supervisor 拿到全量只读工具，写工具一律不暴露。"""
    names = {t.name for t in await react_agent._build_finance_tools("supervisor")}
    assert len(names) >= 10
    assert not (names & agent.WRITE_EXCLUDED), "运行时只暴露只读工具"


async def test_build_finance_tools_bookkeeping_subset(temp_db) -> None:
    """bookkeeping 只看账本类只读工具（record_transaction 是写工具，须被排除）。"""
    names = {t.name for t in await react_agent._build_finance_tools("bookkeeping")}
    assert names == {"get_ledger_view", "get_budget", "get_trend"}


async def test_build_finance_tools_portfolio_includes_market(temp_db) -> None:
    names = {t.name for t in await react_agent._build_finance_tools("portfolio")}
    assert {"get_market_view", "get_quote", "search_symbol"} <= names


async def test_build_finance_tools_honors_agent_config(temp_db) -> None:
    """设置页的工具开关真正生效：配置为子集时只暴露交集（写工具仍被排除）。"""
    cfg = await agent_config.get_config()
    cfg.setdefault("agents", {}).setdefault("portfolio", {})["tools"] = ["get_quote", "sell_position"]
    await db.set_setting("agent_config", json.dumps(cfg, ensure_ascii=False))
    names = {t.name for t in await react_agent._build_finance_tools("portfolio")}
    # get_quote 保留；sell_position 是写工具被 WRITE_EXCLUDED 排除
    assert names == {"get_quote"}


def test_make_langchain_tool_required_args_schema() -> None:
    """动态 args_schema 正确区分必填/可选参数（create_model 路径回归）。"""

    async def impl(args: dict) -> str:
        return "ok"

    tool = react_agent._make_langchain_tool(
        name="get_quote",
        description="查询行情",
        impl=impl,
        param_schema={
            "properties": {
                "symbol": {"type": "string", "description": "6 位代码"},
                "limit": {"type": "integer", "description": "返回点数"},
            },
            "required": ["symbol"],
        },
    )
    fields = tool.args_schema.model_fields
    assert fields["symbol"].is_required()
    assert not fields["limit"].is_required()
