"""MCP 客户端端到端测试：用一个真实 MCP StreamableHTTP 服务器验证客户端 discover/call。

服务器用标准库 http.server 实现协议核心（initialize / tools/list / tools/call，
外加规范要求的 GET→405 与 notification→202），客户端 mcp_client.refresh 拉取工具
→ call_mcp_tool 调用，验证官方 mcp SDK 全链路真实可用。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from app import mcp_client

# ---------------------------------------------------------------------------
# 一个真实的最小 MCP StreamableHTTP 服务器（本地代码起服务）
# ---------------------------------------------------------------------------


class _MCPHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D401 — 静默
        pass

    def _send(self, obj: dict[str, Any]) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reply(self, payload: dict[str, Any], result: Any) -> None:
        self._send({"jsonrpc": "2.0", "id": payload.get("id"), "result": result})

    def do_GET(self):  # noqa: N802
        # MCP 规范：不支持 GET SSE 流的服务器应返回 405，客户端需容忍
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if "id" not in payload or payload.get("id") is None:
            # notification（如 notifications/initialized）：无需响应，返回 202
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        method = payload.get("method")
        if method == "initialize":
            self._reply(payload, {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-mcp", "version": "1.0"},
            })
        elif method == "tools/list":
            self._reply(payload, {"tools": [
                {"name": "echo", "description": "回显文本",
                 "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
                {"name": "add", "description": "两个数相加",
                 "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}},
            ]})
        elif method == "tools/call":
            params = payload.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "echo":
                content = f"echo:{args.get('text', '')}"
            elif name == "add":
                content = f"sum={args.get('a', 0) + args.get('b', 0)}"
            else:
                content = f"unknown:{name}"
            self._reply(payload, {"content": [{"type": "text", "text": content}]})
        else:
            self._send({"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32601, "message": "method not found"}})


@pytest.fixture
async def mcp_up(tmp_path, monkeypatch):
    """起本地 MCP 服务器 + 写配置 + 指向 mcp_client。"""
    # 1) 起 HTTP 服务
    httpd = HTTPServer(("127.0.0.1", 0), _MCPHandler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    # 2) 配置
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({
        "servers": [{"name": "test", "url": f"http://127.0.0.1:{port}/mcp"}]
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(mcp_client, "MCP_CFG", cfg)
    mcp_client._servers.clear()
    yield
    httpd.shutdown()
    mcp_client._servers.clear()


async def test_mcp_refresh_discovers_tools(mcp_up) -> None:
    """refresh 能发现 MCP 服务器工具并转成 function schema。"""
    schemas = await mcp_client.refresh()
    names = {s["function"]["name"] for s in schemas}
    assert {"mcp__echo", "mcp__add"} <= names
    echo = next(s for s in schemas if s["function"]["name"] == "mcp__echo")
    assert "text" in echo["function"]["parameters"]["properties"]


async def test_mcp_call_tool(mcp_up) -> None:
    """call_mcp_tool 真实调用服务器工具并返回文本结果。"""
    await mcp_client.refresh()  # 先建立会话
    r = await mcp_client.call_mcp_tool("test", "echo", {"text": "你好"})
    assert r == "echo:你好"
    r2 = await mcp_client.call_mcp_tool("test", "add", {"a": 3, "b": 4})
    assert r2 == "sum=7"


async def test_mcp_resolve(mcp_up) -> None:
    """resolve_mcp_tool 能识别 MCP 工具名。"""
    await mcp_client.refresh()
    assert mcp_client.resolve_mcp_tool("mcp__add") == ("test", "mcp__add")
    assert mcp_client.resolve_mcp_tool("not_a_tool") is None