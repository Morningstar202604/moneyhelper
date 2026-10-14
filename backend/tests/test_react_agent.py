"""react_agent 工具装配回归测试。

锁定两个曾导致 LangGraph react 路径每次静默降级的缺陷：
- `_build_finance_tools` 曾引用未导入的 `agent.WRITE_EXCLUDED`（NameError，每次请求降级手写 loop）
- `_make_langchain_tool` 曾用 `type()` 直接建 pydantic 模型（pydantic 2 报
  "A non-annotated attribute was detected"，工具装配必失败）
"""

from __future__ import annotations

from app import agent, react_agent


def test_build_finance_tools_supervisor_gets_readonly_tools() -> None:
    """supervisor 拿到全量只读工具，写工具一律不暴露。"""
    names = {t.name for t in react_agent._build_finance_tools("supervisor")}
    assert len(names) >= 10
    assert not (names & agent.WRITE_EXCLUDED), "运行时只暴露只读工具"


def test_build_finance_tools_bookkeeping_subset() -> None:
    """bookkeeping 只看账本类只读工具（record_transaction 是写工具，须被排除）。"""
    names = {t.name for t in react_agent._build_finance_tools("bookkeeping")}
    assert names == {"get_ledger_view", "get_budget", "get_trend"}


def test_build_finance_tools_portfolio_includes_market() -> None:
    names = {t.name for t in react_agent._build_finance_tools("portfolio")}
    assert {"get_market_view", "get_quote", "search_symbol"} <= names


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
