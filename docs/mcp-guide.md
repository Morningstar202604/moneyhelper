# 把小满接进你的 AI（MCP）
小满内置 MCP Server：Claude Code / Cursor / 任何 MCP client 可直接操作你的账本。
## Claude Code
```bash
claude mcp add xiaoman -- python -m app.mcp_server
```
## 验证
对 AI 说：「帮我记一笔 打车 32 元」→「这个月餐饮花了多少」
> 工具清单见 `backend/app/mcp_server.py`（20+ 工具持续全量化中）
