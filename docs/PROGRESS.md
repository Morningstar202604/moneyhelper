# 实施进度

> 单一进度真源。任何"还剩什么"的问题看这一页，不需要回头读规划文档。
> 计划本身见 [PLAN-DETAILED.md](PLAN-DETAILED.md)，本页只记状态。
>
> 更新规则：每完成一个里程碑就改这一页，并在末尾追加一行变更记录。

最后更新：2026-10-19 · 基线 `5e74088`（后端 659 测试 / 前端 86 单测 + 15 e2e）

## 总览

| 里程碑 | 完成度 | 状态 |
|---|---:|---|
| M0 稳固+补课 | 100% | 完成 |
| M1 模块化+文档骨架 | 100% | 完成 |
| M2 协议补课 | 100% | 完成 |
| M3 财务部门模式 | 70% | 工单/LLM 派工/部门 agent/对账/SSE 完成；缺呈批 HITL 与前端工位图 |
| M4 多端 | 33% | CLI 可用，桌面/发版未做 |
| M5 可视化+适老 | 20% | 图表缺 5 项，适老/语音未做 |
| M6 生态+获客 | 10% | 基本未开始 |

## M0 稳固+补课 · 完成

| 项 | 产出 |
|---|---|
| M0.1 litellm 键名 | `llm.py` 用 `cfg.get("key")` |
| M0.2 多段记账原子性 | `db.add_transactions_batch` + 写锁串行化 |
| M0.3 402→400 | 校验失败返回 400 |
| M0.4 mem.remember 阻塞 | `asyncio.to_thread` |
| M0.5 tiktoken 声明 | requirements 显式声明 |
| M0.6 P2 批处理 | 限流首请求计数、metrics 移出白名单、审计归属 ContextVar |
| M0.7 逐文件通读 | `docs/module-map.md`（脚本生成，81 模块） |
| M0.8 harness 调研 | `docs/planning/11-agent-harness-专项调研.md` |
| M0.9 仓库瘦身 | 已删 doc-fetch-resources；CI 大文件检查 ≤1MB |

后续补修（审计发现计划里声称完成但有缺口）：
- litellm `retry_policy.retry_timeout` 是无效字段 → 改顶层 `timeout`
- DeepSeek `reasoning_content` 声称支持但未实现 → 按 `reasoning` 来源单列
- `.env.example` 缺 7 个在用变量 → 补齐

## M1 模块化+文档骨架 · 完成

| 项 | 产出 |
|---|---|
| M1.1 包骨架 | `xiaoman/{core,server,cli,mcp}` 分层门面 + CLI（add/ls/report/balance/ask/serve） |
| M1.2 db 拆分 | `app/db/` 14 个域模块 + `_schema.py`；`_core.py` 793→471 行 |
| M1.3 连接池 | 1 写连接 + 3 读连接（WAL 只读）；`get_write_lock()` 串行化写事务 |
| M1.4 main.py 拆薄 | 1827→222 行；`system.py` 再拆 9 个域模块；70 端点零差异 |
| M1.5 文档站 | mkdocs-material + strict 构建；`deploy/one-click.sh`；CI hygiene job |

## M2 协议补课 · 80%

| 项 | 状态 | 说明 |
|---|---|---|
| M2.1 工具 schema pydantic 化 | 完成 | `app/tool_schemas.py` 31 个模型为单一真源；修两侧参数漂移 |
| M2.2 MCP 全量 + Streamable HTTP | 完成 | 31 工具；`/mcp` 无斜杠可用；SSE 保留至 `/mcp-sse/sse` |
| M2.3 HITL 迁 Elicitation | 完成 | `app/approval.py`；MCP 写工具 fail-closed 审批 |
| M2.3 晨报迁 Tasks | **阻塞** | mcp SDK 只有 experimental；fastmcp 2.12 未透传。见下 |
| M2.4 AG-UI 映射层 | 完成 | `app/agui.py` + `POST /api/ask/agui`；流式翻译，双协议共存 |
| M2.5 官方 saver 替换 | 完成 | `AsyncSqliteSaver` + `WeakKeyDictionary` 按 loop 缓存；pending 表加 TTL 清理 |

M2.3 Tasks 阻塞细节：`mcp` 1.30 把 Tasks 放在 `mcp.server.experimental`
（`TaskSupport` / `ServerTaskContext`），标 experimental；`fastmcp` 2.12 源码里
搜不到 task 实现。要落地需绕开 fastmcp 直接用 lowlevel server，风险大于收益。
fastmcp 支持后只换装饰器，业务实现不动。

## M3 财务部门模式 · 70%

| 项 | 状态 |
|---|---|
| M3.1 工单 schema | 完成：`dept_models.py` pydantic 模型（dept/status 枚举、budget_tokens、metrics） |
| M3.2 LLM 派工 | 完成：`dept_dispatch.py`，schema 校验 + 工具白名单过滤 + 失败回落规则 |
| M3.3 部门 agent | 完成：`dept_agent.py`，独立 instructions + 工具白名单 + 独立 thread_id + token 预算；模型不可用退回确定性 |
| M3.4 秘书交叉对账 | 完成核心：按结构化 metrics 比对，冲突指明部门；呈批件含结论/冲突/发现 |
| M3.5 老板呈批 HITL | 未做（下一步） |
| M3.6 部门实况看板 | 后端完成：`/api/department/stream` SSE + dept_activity 事件；前端工位图未做 |

这是计划里的"核心差异化"，也是当前最大缺口。

## M4 多端 · 33%

| 项 | 状态 |
|---|---|
| M4.1 CLI | 可用（argparse；add/ls/report/balance/ask/serve；本地+远程双形态）。缺：typer+rich、`xm dept run` |
| M4.2 Tauri 桌面 | 未做 |
| M4.3 发版自动化 | 未做（无 semantic-release、无 release workflow） |

## M5 可视化+适老 · 20%

| 项 | 状态 |
|---|---|
| M5.1 适老模式 | 未做（无字号档位/高对比主题） |
| M5.2 ECharts 图表 | 2/7：净资产、预算进度已成；缺现金流瀑布、支出树图、订阅时间线、五维雷达、部门看板 |
| M5.3 后端预聚合 | 部分：`analysis` 做计算但无 SQL GROUP BY + TTL 缓存 |
| M5.4 语音闭环 | 未做 |
| M5.5 反事实沙盒 | 未做（计划标注"若排期允许"） |

## M6 生态+获客 · 10%

| 项 | 状态 |
|---|---|
| M6.1 审计底稿 PDF | 未做 |
| M6.2 挑战赛+错误台账 | 未做 |
| M6.3 模型招聘 eval | 部分：有 `evaluate.py`，缺 50 题题库与排行榜 |
| M6.4 家庭议会 | 未做（有成员管理，无多人审批链） |
| M6.5 教程三连+MCP Registry | 未做 |
| M6.6 可复核性标准草案 | 未做 |

## 下一步顺序

1. M3.5 呈批 HITL → M3.6 前端工位图
2. M4.3 发版自动化（比 M4.2 桌面端性价比高）
3. M5.2 补齐 5 个图表

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-18 | 建立本页；M0/M1 完成，M2 达 80% |
| 2026-10-18 | M2.4 AG-UI 映射层完成，M2 达 90% |
| 2026-10-18 | M2.5 完成，M2 收官；pending 表补 TTL 清理 |
| 2026-10-19 | M3.1 工单模型 + 结构化对账 + 部门 SSE 流完成，M3 达 40% |
| 2026-10-19 | M3.2 LLM 派工 + M3.3 部门 agent 完成，M3 达 70% |
