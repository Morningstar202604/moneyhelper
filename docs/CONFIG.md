# 配置说明（环境变量 + 应用设置项）

小满分两层配置：**环境变量**（启动前，`backend/.env`，复制自 `.env.example`）与**应用设置**（运行时，设置页，落库到 SQLite `settings` 表，立即生效）。

## 1. 环境变量（backend/.env）

全部可选；不配置也能完整运行（确定性模板兜底，无 AI 也能记账/分析/出晨报）。

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容端点。国产推荐：DeepSeek / 豆包（火山方舟）/ 通义千问 / 云知声（详见下方「AI 端点速查」） |
| `LLM_API_KEY` | 空 | 模型密钥；也可不配，启动后在设置页填 |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `API_TOKEN` | 空 | 访问口令。空 = 不鉴权（仅限本机/内网）；设置后 `/api/*` 需 Bearer/`?token=`，前端弹口令框 |
| `ALLOWED_HOSTS` | 空 | 未设口令时额外放行的 Host（逗号分隔）。默认只放行本机 |
| `CORS_ALLOW_ALL` | 空 | 调试用：仅放行前端开发源（`1` 开启）。生产同域托管无需改动 |

> 提示：AI 配置以**应用内设置页为准**（`ai_base_url` / `ai_api_key` / `ai_model` / `ai_enabled`），落库后优先级高于环境变量，重启不丢。

## 2. 应用设置项（设置页，落库）

| 设置项 | 键 | 取值 | 说明 |
|---|---|---|---|
| 默认首页 | `default_tab` | `chat`（默认）/ `overview` / `holdings` / `market` / `ledger` | 启动/刷新后落地的页签 |
| 涨跌颜色 | `color_scheme` | `cn`（红涨绿跌，默认）/ `us`（绿涨红跌） | 全局涨跌色即时切换 |
| 语言 | `lang` | `zh` / `en` | 界面双语（含空态、能力清单、设置项） |
| 数字格式 | `compact_numbers` | `on` / `off` | 大额显示为 1.3万 / 5000 |
| 快捷建议 | `show_suggestions` | `on` / `off` | 问答输入框下方快捷指令 chips |
| 自动刷新 | `auto_refresh` / `auto_refresh_seconds` | `on`/`off` / 秒数（默认 300） | 总览行情自动轮询 |
| 展示导出 | `show_export` | `on` / `off` | 是否显示导出入口 |
| 过程展开 | `expand_process` | `on` / `off` | 问答中 agent 工具调用过程默认展开/折叠 |
| 语音输入 | `voice_input` | `on` / `off` | 语音输入开关 |
| 月收入 | `monthly_income` | 数字 | 预算/储蓄率/应急金计算基准 |
| 应急金目标 | `emergency_target_months` | 数字（默认 6） | 覆盖月数目标 |
| 必要支出类别 | `essential_categories` | 逗号分隔（默认 居住,餐饮,交通） | 预算/超支分析口径 |
| 本月预算 | `budgets`（API） | 数组 `[{category,amount}]`，`__total` 为总预算 | 设置页 → 预算；总览实时进度 |
| 财务目标 | `goals`（API） | `{name, target, note}` | 设置页 → 账本规则 → 目标 |
| 晨报时间 | `report_time` | `HH:MM`（默认 08:00） | 每日晨报生成时间 |
| 行情来源 | `quote_source_mode` | `auto`（默认）/ `eastmoney` / `sina` / `snapshot` | 三级降级；`snapshot` 只用组合库快照价 |
| 访问口令 | — | 见 `API_TOKEN` | 设置页 → 访问口令（Bearer 鉴权 + 401 弹窗） |
| 长期记忆 | `memory`（API） | 文本条目 | 设置页 → 长期记忆；问答优先参考 |

## 3. AI 端点速查（国产优先）

| 服务商 | Base URL | 模型示例 | 备注 |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | 默认预设 |
| 豆包（火山方舟） | `https://ark.cn-beijing.volces.com/api/v3` | 推理接入点 ID | 需先开通接入点 |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | |
| 云知声 | `https://maas-api.unisound.com/v1` | `u2-flash` | 实测流式回答 + 工具循环正常 |

模型能力要求：OpenAI 兼容 `/chat/completions`，支持 **流式（SSE）** 与 **function calling**（工具循环场景必需）。不满足时 app 自动降级确定性路径，服务不中断。

## 4. 变更校验

- 设置写入经 `PUT /api/settings` 校验：数值区间、on/off 枚举、`HH:MM` 格式、行情源枚举、URL 前缀等，非法项逐条报错、合法项逐条生效。
- 备份口令不落库、不进入导出包明文；导出明文有强提示。
