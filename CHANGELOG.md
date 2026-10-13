# Changelog

项目版本号与发布历史。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本语义遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [1.4.0] - 2026-10-07（安全加固 + 前端渲染修复 + 测试覆盖提升 + 订阅/撤回/预算）

> 定位：安全漏洞全面修复；空白页根因治理；CI 真正跑测试；订阅到期巡检+撤回面板+预算/订阅卡片落地。

### 安全修复

- **P0 `/mcp` 鉴权绕过**：`mount_to_app` 新增 `_McpAuthGuard`（`BaseHTTPMiddleware`），对 `/mcp` 路径强制校验 `API_TOKEN`，关闭"挂载 ASGI 子应用绕过主中间件链"的缺口
- **P0 MCP 工具命名隔离**：外部 MCP 工具统一加 `mcp__` 前缀，防止与内置财务工具命名冲突及 prompt injection 误调用
- **P0 SQL LIKE 通配符注入**（`db.search_runs`）：转义 `%` / `_` / `\`，加 `ESCAPE '\'` 子句，杜绝用户输入被当通配符引发全表扫描
- **P1 备份口令 SSE 泄漏**：`tool_backup_now` 返回文本不再含明文口令，口令仅通过独立 `passphrase` 字段一次性传递
- **P1 登录限流分布式爆破**：`auth.login()` 注入 `FastAPI Request`；支持 `X-Forwarded-For` 取真实 IP；额外按用户名限流
- **P1 `ai_enabled` 工具层拒绝**：从 `SETTING_KEYS_ALLOWED` 移除 `ai_enabled`，防止模型静默关闭 AI 功能
- **P1 LLM 配置读取静默吞异常**：`llm._config()` DB 失败改为 `_log.warning`，区分"未接入"与"配置损坏"

### 前端修复

- **白屏根因**：`main.tsx` 中 `I18nProvider` 提升至 `ErrorBoundary` 外层，消除 `useI18n()` 在 Provider 外 throw 导致整树崩溃

### 工程化

- **CI/CD**：`.github/workflows/ci.yml` 后端段新增 `pytest` 运行（289 用例），前端段新增 `vitest run`（31 用例），CI 真正成为质量门禁
- **文档**：`CHANGELOG` 版本降序重排；中英文 README 版本号统一；`CONTRIBUTING.md` 端口号修正；删"AI生成"残留标记
- **Git**：移除 remote URL 中的 PAT 凭据明文

### 来自 1.3.x/1.2.x（保留条目）

- **订阅到期巡检**：`app.scheduler.subs_due_check` CronTrigger Asia/Shanghai，7 天窗口，月度幂等去重写入 `user_memory`
- **通用撤销面板**：`CommandPalette`（Cmd+K）撤销分组，`POST /api/undo/{record_id}` 撤回
- **Dashboard 预算卡**（`BudgetCard`）三档配色 + 红色超支徽标 + 分类进度行 + 无预算引导
- **订阅待缴卡**（`SubscriptionsCard`）前端纯 hook 计算 7 天内到期项；今日红/3 天黄
- **BudgetSection 实时预览**：分类输入即时渲染堆叠进度条，溢出红提示
- **新增端点**：`GET /api/subscriptions` + `GET /api/undoables` + `POST /api/undo/{record_id}` + `DELETE /api/memory?kind=`

## [1.3.0] - 2026-10-05（撤回 + 规则引擎 + 限流 + 前端单测）

> 定位：让应用在「可用」之上进一步「可逆、可自治、可回归」——写错能撤回、分类能自学习、接口能被保护、前端能被单测约束。

### 新增

- **SQLite 快照式 undo**：每笔写交易/持仓/负债/订阅落库前 `_record_snapshot`，撤回时 `_restore_from_snapshot` 还原。单条 + 批量撤回，零新依赖
- **JSON DSL 分类规则引擎**（`backend/app/rules.py`）：`desc_contains`/`desc_regex`/`category_is`/`amount_min`/`amount_max`，priority 数字大者优先，命中即短路
- **in-memory 滑动窗口 API 限流**：200 次/分钟/IP，429 + `Retry-After`；`/api/health` 与 `/api/metrics` 不计。绕过 slowapi 依赖
- **vitest + RTL + jsdom 前端单测**：覆盖 `i18n`/`store`/`AlertBanner` = 16 项

### 工程化

- 后端 282 用例全绿；前端 16 用例全绿
- Playwright 11 项 e2e（smoke×5 + chat×2 + data×4）在位
- `test_rate_limit.py` 4 项专项测限流行为

## [1.2.1] - 2026-10-05（去自研发化 + 前端安全/性能加固 + e2e 补齐）

> 定位：消除重复造轮子；收紧前端安全与性能基线；补齐端到端测试短板。

### 重构

- backend/mcp_client.py：自研 JSON-RPC + StreamableHTTP 帧重试移除，改用官方 `mcp.ClientSession` + `streamable_http_client`
- backend/db.py memory_retrieve：手写 Okapi BM25 换为 `rank_bm25.BM25L`；保留中文二元组分词

### 安全

- ReactMarkdown 输出过 `rehype-sanitize` 阻断脚本注入
- DataSection.importBackup：探测明文/加密备份，差异化提示

### 性能

- FinishedMessages 消息虚拟化窗口，长会话 DOM 节点下降约 10 倍
- build：esbuild `pure: [console.log/debug/info]` 剔除生产 console

### 依赖

- + `mcp>=1.0,<2` / `rank-bm25>=0.2,<1` (backend)
- + `rehype-sanitize` / `@playwright/test@1.63.0` (frontend)

### 测试

- Playwright 端到端 11 项冒烟 + 问答 + 功能页

## [1.2.0] - 2026-10-05（Agent 智能体升版）

> 定位：Agent 路线图 P0/P1/P2 全部落地，真实模型端到端联调与质量安全收尾。

### 新增

- **Agent P0**：长会话摘要压缩；模型点亮/可用性探测 + 自动降级
- **Agent P1**：记忆分层（会话/长期/经验）+ BM25 语义检索 + 经验库反思 + 主动遗忘
- **Agent P2**：多 Agent 编排（supervisor → 财务/通用/记忆）；审计日志；MCP 客户端；附件上传
- 真实 AI 端到端联调 + 压力测试（20 并发写 / 15 混合读写 / 极端输入全 422）

### 修复

- 空库 agent 降级误报「总市值 0」→ 改走「还没有录入」引导
- conftest 注入 `_no_real_llm`，全量 5–6 分钟降到 42.8s

### 工程化

- 后端 269 用例全绿（42.8s）、覆盖率 77%（核心模块 90%+）
- 前端生产构建通过

## [1.0.0] - 2026-10-01（正式版）

> 定位：**本地运行 × 云端能力**。对话界面中枢；数据 100% 本地存储；国产 AI 端点。

### 新增

- 5 页签投资者心智前端；17 个 agent 工具；财务目标/长期记忆/体检（5 维度）+ 晨报
- PBKDF2 + Fernet 加密备份（口令一次性展示）；行情三级降级；空库首启引导
- 双语 UI + 高度自定义（默认首页/涨跌色/语言/轮询…）

### 修复

- 理财咨询句不被记账劫持；6 位代码买入不错记支出；晨报递归修复
- 安全：agent 模式只暴露读类工具（7 个写工具从模型侧移除）；`tool_set_setting` 白名单

### 工程化

- 182 测试全绿；覆盖率 75%+
- 开源化：中英文 README + 真实截图 + SEO + docs 五件套

## [0.9.0] - 2026-09（投资者心智重构 + 工作流）

- 5 页签导航、指数条、持仓分组 + 集中度风控、行情自选/搜索/K 线、17 个 agent 工具

## [0.8.0] - 2026-09（目标 · 记忆 · 体检）

- 财务目标、长期记忆、5 维度体检；对话中"记住…"直存

## [0.7.0] - 2026-09（LangGraph 单路径）

- LangGraph 图成为唯一执行路径；React 19 / Vite 7 / Tailwind 4

## [0.6.0] - 2026-09（Agent 升级）

- 真实 agent 工具循环、K 线、备份/恢复、Docker、一键启动

## [0.5.0] - 2026-09

- 预算、记账、CSV 导入、PWA、会话搜索、AI 问答、品牌系统
