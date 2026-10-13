"""MCP 客户端：基于官方 `mcp` SDK（StreamableHTTP 传输），不自研协议实现。

历史说明：此前曾为避免依赖冲突手写过 JSON-RPC 客户端；实测官方 mcp SDK 与
本项目 FastAPI/httpx/starlette 版本零冲突（httpx>=0.27 兼容 0.28），按
「能用成熟库不自研」原则整体替换——协议握手、会话 ID、SSE 流解析、
notifications 时序等全部交给 SDK，本模块只剩配置/适配两层薄逻辑。

配置：`backend/data/mcp.json`（不存在则空）：
```json
{
  "servers": [
    {
      "name": "calculator",
      "url": "http://127.0.0.1:9100/mcp"
    }
  ]
}
```

流程：refresh 时对每个 server 打开一条 StreamableHTTP 会话（SDK 自动完成
initialize 握手）→ list_tools 拉取工具清单并转成 function schema 供 LLM 调用；
call_mcp_tool 时新开会话 → call_tool。会话由 SDK 的 async context 管理，
用完即关（外部工具低频调用，无需常驻连接）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .logging_utils import get_logger

_log = get_logger("mcp")

MCP_CFG = Path(__file__).resolve().parent.parent / "data" / "mcp.json"
TIMEOUT = 15.0

# 进程内工具注册表：server_name -> [tool names]（供 resolve_mcp_tool 解析归属）
_servers: dict[str, list[str]] = {}


def _load_config() -> list[dict[str, Any]]:
    try:
        if not MCP_CFG.exists():
            return []
        data = json.loads(MCP_CFG.read_text(encoding="utf-8") or "{}")
        return data.get("servers") or []
    except Exception:  # noqa: BLE001 — 配置异常按无 MCP 处理
        _log.warning("mcp config parse failed")
        return []


@asynccontextmanager
async def _open_session(url: str) -> AsyncIterator[ClientSession]:
    """打开一条 StreamableHTTP 会话并完成 initialize 握手（SDK 全托管）。

    新版 SDK 不再收 timeout 参数，改由调用方传入自建 httpx.AsyncClient；
    客户端生命周期归本函数管理（SDK 只管 MCP 会话本身）。
    """
    http = httpx.AsyncClient(timeout=TIMEOUT)
    try:
        async with (
            streamable_http_client(url, http_client=http) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield session
    finally:
        await http.aclose()


def _make_schema(tool: Any) -> dict[str, Any]:
    """把 mcp.types.Tool 转成 OpenAI function-calling schema。

    外部 MCP 工具统一加 mcp__ 前缀：防止与内置工具命名字典冲突，
    同时让模型一眼区分"本地财务工具"和"外部 MCP 工具"，降低 prompt injection 时误调用概率。"""
    schema = getattr(tool, "inputSchema", None)
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": f"mcp__{getattr(tool, 'name', 'tool')}",
            "description": (getattr(tool, "description", "") or "")[:300],
            "parameters": schema,
        },
    }


def _content_text(content: Any) -> str:
    """把 CallToolResult.content 里的文本块拼成一个字符串。"""
    out: list[str] = []
    for c in content or []:
        text = getattr(c, "text", None)
        if isinstance(text, str):
            out.append(text)
    return "".join(out)


async def _discover(server: dict[str, Any]) -> list[Any]:
    """对单个服务器 list_tools，返回工具对象列表并登记注册表。"""
    name = server.get("name") or "mcp"
    async with _open_session(server["url"]) as session:
        resp = await session.list_tools()
    tools = list(resp.tools)
    _servers[name] = [f"mcp__{t.name}" for t in tools]
    return tools


async def refresh() -> list[dict[str, Any]]:
    """刷新并返回所有 MCP 服务器提供的工具 schema（供 agent 装配）。"""
    out: list[dict[str, Any]] = []
    for server in _load_config():
        try:
            for t in await _discover(server):
                schema = _make_schema(t)
                if schema:
                    out.append(schema)
        except Exception as exc:  # noqa: BLE001 — 单台失败不影响其它
            _log.warning("mcp discover %s failed: %s", server.get("name"), exc)
    return out


async def call_mcp_tool(server_name: str, tool_name: str, args: dict[str, Any]) -> str:
    """调用某 MCP 服务器的某个工具，返回文本结果。找不到返回错误串。

    tool_name 传入时可能含 mcp__ 前缀——剥掉后再发往 MCP 服务器（服务器端保留原始名称）。"""
    raw_name = tool_name.removeprefix("mcp__")
    for server in _load_config():
        if server.get("name") != server_name:
            continue
        try:
            async with _open_session(server["url"]) as session:
                result = await session.call_tool(raw_name, args or {})
            if result.isError:
                return json.dumps(
                    {"error": _content_text(result.content) or "mcp tool error"},
                    ensure_ascii=False,
                )
            text = _content_text(result.content)
            return text or json.dumps(
                result.model_dump(exclude_none=True), ensure_ascii=False, default=str
            )
        except Exception as exc:  # noqa: BLE001
            return f"mcp 工具调用失败：{type(exc).__name__}: {exc}"
    return f"mcp 服务器 {server_name} 未配置"


def resolve_mcp_tool(name: str) -> tuple[str, str] | None:
    """把 `tool` 名解析为 (server_name, tool_name)；非 MCP 工具返回 None。"""
    for sname, tools in _servers.items():
        if name in tools:
            return sname, name
    return None
