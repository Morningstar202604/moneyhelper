# 把小满接进你的 AI（MCP）

小满内置 MCP Server，Claude Code / Cursor / Cline / 任何 MCP 客户端都能直接读写你的账本。
数字全部来自本地确定性计算，模型只负责决定"调哪个工具"。

## 两种接入形态

| 形态 | 何时用 | 地址 |
|---|---|---|
| Streamable HTTP（推荐） | 小满服务已在运行（Docker / `xiaoman serve`） | `http://<host>:8788/mcp` |
| stdio | 由 IDE 直接拉起子进程，不需要常驻服务 | `python -m app.mcp_server stdio` |

> 传输层从 2.1.0 起默认 Streamable HTTP（MCP 规范 2025-03 起推荐）。
> 旧的 SSE 端点保留一个版本期，地址是 `http://<host>:8788/mcp-sse/sse`，
> 供已接入的老客户端继续使用。

## Claude Code

Streamable HTTP（服务已在运行）：

```bash
claude mcp add --transport http xiaoman http://127.0.0.1:8788/mcp
```

stdio（无需常驻服务，由 Claude Code 拉起）：

```bash
claude mcp add xiaoman -- python -m app.mcp_server stdio
```

设了 `API_TOKEN` 时需带口令：

```bash
claude mcp add --transport http xiaoman \
  http://127.0.0.1:8788/mcp --header "Authorization: Bearer $API_TOKEN"
```

## Cursor / 其他客户端

在 MCP 配置文件里加（`~/.cursor/mcp.json` 或客户端对应位置）：

```json
{
  "mcpServers": {
    "xiaoman": {
      "url": "http://127.0.0.1:8788/mcp",
      "headers": { "Authorization": "Bearer <你的 API_TOKEN>" }
    }
  }
}
```

`headers` 在未设 `API_TOKEN` 时可省略。

## 可用工具

工具清单的唯一真源是 `backend/app/tool_schemas.py`，共 31 个：

| 类别 | 工具 |
|---|---|
| 组合与账本 | `get_market_view`、`get_ledger_view`、`get_risk_flags`、`get_budget`、`get_trend`、`get_goals`、`get_health_check` |
| 行情 | `search_symbol`、`get_quote`、`get_kline`、`get_watchlist`、`add_to_watchlist`、`remove_from_watchlist` |
| 记账与持仓 | `record_transaction`、`record_position`、`sell_position`、`import_transactions` |
| 计算 | `get_net_worth`、`get_financial_health`、`get_returns`、`get_goal_progress` |
| 家庭与审计 | `get_family_summary`、`get_provenance` |
| 记忆 | `get_user_memory`、`save_user_memory`、`get_lessons` |
| 设置与产出 | `set_setting`、`trigger_morning_report`、`backup_now` |
| 通用 | `get_now`、`web_search` |

## 验证

对 AI 说：

1. 「帮我记一笔 打车 32 元」→ 应调用 `record_transaction`
2. 「这个月餐饮花了多少」→ 应调用 `get_ledger_view`
3. 「我有什么风险」→ 应调用 `get_risk_flags`

三步都拿到真实数字即接入成功。若工具列表为空，先检查 `/api/health` 是否可达、
以及是否设了 `API_TOKEN` 却没带口令。

## 安全说明

`/mcp` 与 `/mcp-sse` 都经过与小满主应用同一套鉴权：设了 `API_TOKEN` 时
必须带 `Authorization: Bearer <token>` 或 `?token=`。**不要在没有口令的情况下
把端口暴露到公网**——MCP 暴露的是全量财务工具，包括卖出持仓与备份导出。
