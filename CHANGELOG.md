# Changelog

项目版本号与发布历史。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本语义遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [2.8.0] - 2026-10-21（前端重构：对齐 ChatGPT 的对话界面范式）

> 用户反馈"前端拉垮、不要自己乱做"。本轮不发明设计，按 ChatGPT 已验证的界面结构重排。

### 布局
- 侧栏改为浅灰底（`--sidebar`），主区纯白：只有发送键/焦点态保留品牌绿，交互底色一律中性灰，
  不再整屏泛绿。
- 侧栏结构对齐 ChatGPT：品牌（名称+标语）→「新对话」→ 搜索 → 今天/过去 7 天/更早 分组 →
  底部功能入口（总览/定时产出/财务部门/晨报/设置）。会话项悬停才出重命名/删除。
- 顶栏压成 48px 无分割线工具条：移动端导航 + 品牌，右侧仅语言/明暗/设置三个弱化图标。
- 对话列固定 `48rem` 居中；用户消息改为中性灰圆角气泡（原为绿色），助手消息无容器、
  左侧品牌头像 + 可读宽度正文。
- 空态：品牌标记 + 一句话标题 + 4 个带图标的建议卡（有账本数据时用后端按真实数据生成的建议）。
- 输入器改为 ChatGPT 式圆角容器：附件、文本域、语音、发送同处一框，聚焦时整块抬起。
- 助手操作条（复制/重新生成/下载）移到回答下方，悬停显示。
- 移除右侧常驻 Agent 面板：计划与工具调用在回答内已有内联展示，侧栏只会挤压对话。

### 排版与细节
- 新增 `.md-body` 排版规范：16px / 1.75 行高、标题层级、列表缩进、表格与引用块边界，
  Markdown 回答的阅读密度对齐 ChatGPT。
- 新建会话改为立即切到临时线程（此前会先停在旧会话，需等接口返回才切换）。
- 设置页改为独立全屏页：顶部标题 + 关闭，内容区居中 `max-w-5xl`；桌面侧栏去掉卡片描边。
- 移动抽屉背景统一为侧栏灰，去掉与内容区不一致的卡片白。
- 助手显示名与首屏标题随界面语言切换（英文 Xiaoman / 中文 小满）。
- 删除 `ChatHeader.tsx`、`AgentPanel.tsx` 两个不再使用的组件与相关文案。

### 验证
- `tsc --noEmit` 通过；vitest 111 通过；Playwright e2e 21 通过；`vite build` 通过。
- 1440×900 / 1024×768 / 768×1024 / 390×844 四档截图复核，横向溢出均为 0。

## [2.7.1] - 2026-10-21（专家评审 9 个 P0 全部修复）

> 独立专家评审给出 19/50 打回，逐条修复后复验。

### P0（数据安全 / 功能不可用）

- **迁移备份在 WAL 下是空文件**：`shutil.copy2` 只复制主文件，已提交数据可能全在 `-wal`。
  改用 `sqlite3.Connection.backup()` 生成一致性快照；**备份失败直接中止迁移**（不再"留痕继续"）。
- **迁移非原子**：重建表（DROP+RENAME）无事务，崩溃即永久卡死。整个迁移包进
  `BEGIN IMMEDIATE ... COMMIT`，并新增 `_recover_stale_temp_tables()` 启动清理/恢复遗留临时表。
- **半迁移库永远修不好**：判据从"列是否存在"改为**主键形状**（PRAGMA），
  有 user_id 但主键仍是单列的库能被识别并重建。
- **注册接口必然 500**：passlib 1.7.4 读 `bcrypt.__about__`（bcrypt 5 已移除）导致哈希抛错。
  改为直接用 `bcrypt.hashpw/checkpw`；另修 `_ensure_secret()`（未跑 lifespan 时 JWT secret 为空）。
- **reset 抹掉全实例账本**：`DELETE FROM {t}` 无 WHERE。现在只清当前租户；
  已有用户时未登录调用返回 401。
- **settings / budgets / members 未隔离**：settings 主键改 `(user_id,key)`、
  budgets 改 `(user_id,month,category)`、members 加 `user_id` + `UNIQUE(user_id,username)`；
  `_COMPOSITE_MULTI` 负责旧库重建。
- **备份恢复丢流水**：恢复顺序改为 members → member_loans → transactions；
  `_restore_table` 不再静默 `continue`，失败即抛错整体回滚。
- **编辑 / 合并流水必报错**：多租户改造时补了 SQL 的 `user_id=?` 却漏传实参（6 处）。
- **审计写入提交他人事务**：`add_audit_log` 改为 SAVEPOINT 隔离（与 provenance 一致）。

### 其他

- **CLI 跨事件循环卡死**：读连接池与写连接都绑定事件循环，同一进程连续调用 `asyncio.run`
  会永久等待。读池加 `set_read_pool(False)`（CLI 禁用）、`init_db`/`_read_conn` 检测 loop
  归属、`close_db` 先回滚再带超时关闭；读池的 `mode=ro` 改 `PRAGMA query_only`（WAL 下
  mode=ro 会等写连接 checkpoint）。

### 回归测试

- 新增 `backend/tests/test_p0_regressions.py`（14 项），每条 P0 至少一个用例。
- 全量 737 passed；ruff / tsc / vitest 111 / e2e 21 / mkdocs strict 全绿。

## [2.7.0] - 2026-10-21（可安装性修复 + 多平台产物 + MCP 定时产出）

### 修复（可安装性，实测驱动）

- **`pip install` 出来的包根本跑不起来**：wheel 只含 5 个门面文件（15KB），
  真正的实现在 `backend/app` 下没有被打包；装完 `import xiaoman.server`
  直接 `ModuleNotFoundError: app`。现配置 `package-dir` 同时安装 `app.*`，
  wheel 变为 320KB / 102 个文件；实测从 `C:/Windows` 目录导入成功、
  `xiaoman.server.app` 是真实 FastAPI 实例、CLI `--help` 正常。
- **`pyproject.toml` 依赖漂移**：仍引用已删除的 mem0 / chromadb / opentelemetry /
  langchain-litellm，且 `xiaoman.mcp` 未纳入包列表。已与 requirements 对齐。

### 新增

- **多平台桌面构建工作流** `.github/workflows/desktop.yml`：Windows / macOS / Linux
  三平台矩阵，各自打 PyInstaller 单文件，带"产物能启动并响应健康检查"的冒烟测试，
  tag 触发时自动附加到 Release。
- **MCP 定时产出资源**（Tasks 的可行替代）：
  - `xiaoman://scheduled-outputs` —— 最近 10 条晨报/技能产出
  - `xiaoman://scheduler-status` —— 调度状态
  为什么不用 Tasks：mcp 1.30 的 Tasks 仍是 experimental，fastmcp 2.x 未透传；
  而"客户端能拿到定时产出"用 resource 拉取即可满足，服务端仍由 APScheduler 生成。


### 修复（并行稳定性，根因）

- **审计写入破坏事务边界**：`provenance._persist_entry` 原先复用全局唯一写连接并
  `commit`，会把别的协程未完成的多语句事务一并提交。改为在同一连接上用
  `SAVEPOINT` 局部隔离——既不提交外层事务，也不因独立连接在 Windows 上与主连接
  互等而死锁（两种更简单的做法都实测失败过）。
- **进程级活跃成员状态跨用例泄漏**：`_active_member_id` 是模块级全局字典，
  某用例设置后未清理，会让后续用例把流水挂到"别的库里的成员 id"上，
  触发 `FOREIGN KEY constraint failed`。`temp_db` 与 `test_evaluate` 的
  fixture 现在逐用例清零。修复后连续 8 轮并行回归 723 项全绿（此前约每 5–8 轮
  偶发一次）。

### 验证

- 文档站静态校验：`mkdocs.yml` 的 16 个导航条目全部存在，全仓库文档相对链接 0 坏链
  （本机无法访问 pypi，装不了 mkdocs，故用静态校验替代 `mkdocs build --strict`）。

## [2.6.1] - 2026-10-21（流式断流不再伪装成功）

### 修复

- **半截回答被当成完整结果**：`apiStream` 原先只要收到过任意一帧就把连接关闭当作成功
  （`if (got) return`），断流时用户看到的是一段看似完整的文字，实际缺后半段。
  现在以服务端 `done` 终帧作为完成标志；已收到内容但未收到终帧时如实抛错。
- **错误时隐藏已收到的内容**：`ChatMessageBubble` 原先只要有 error 就整块替换成报错行，
  用户刚看到的文字会消失。现在有正文时保留内容，另起一行提示"回答可能不完整"。

### 测试

- 新增 e2e：拦截 `/api/ask` 只发两帧文本后关闭，断言页面既显示已收到的文字、
  也显示不完整提示。这条用例是驱动上述修复的回归护栏。

## [2.6.0] - 2026-10-21（测试真实性整改 + 权限模型 + 适老化 + 桌面端）

### 测试真实性（重点）

审计发现"看起来有测试、实际没验证"的情况，已整改：

- **`test_dept_agent.py` 的 7 个用例 mock 掉了 `agent.run_agent` 本身**，只验证
  "参数被传下去了"，真正的工具循环/参数解析/结果回填从未执行。新增
  `test_agent_real_loop.py`（6 项）：只桩模型 I/O 边界，让 agent 循环与工具实现
  真实跑起来，断言"工具被真实执行、结果被回填、账本确实变了、写工具不可见"。
- **删除 `ImportPanel.tsx` 及其 3 个假测试**：该组件与 `EntryView` 内的同名实现
  重复，实际是死代码；三条用例都在断言"渲染不报错"，其中一条与另一条完全重复。
- **补强 `test_evaluate`**：原先只断言 200，现验证返回结构（month/refreshed_at/
  summary/items）与每条评估项的字段契约。
- 新增语音 hook 测试 5 项（真实分支：不支持时的提示、识别结果写回、停止复位、语言跟随）。
- 迁移类测试加 `xdist_group` 隔离（会切换全局 DB_PATH，必须与其它用例串行）；
  连续 6 轮并行回归稳定在 721 项。

### 权限模型（方案 B）

对比三种方案后选择"严格隔离 + 管理员只读概览"：
- 每个登录用户只能读写自己的租户数据（角色不能越权读明细，有测试证明）。
- 管理员新增两个端点：`/api/auth/users`（账号列表）、`/api/auth/tenants-overview`
  （各租户**条数**概览）。**只给规模，不给金额/名称/流水**——管理员需要知道
  "多少人在用"，不需要知道"张三花了多少钱"；家庭共享由 members 机制承载。
- 非管理员 403、未登录 401，均有测试。

### 适老化

- 新增设置项 `text_scale`（标准/大/特大）与 `high_contrast`，通过根元素
  `data-*` 驱动全局 CSS：字号基准 16 → 18/20px，高对比加深文字与边框。
- 实测：手机宽度（390px）切到特大 + 高对比后仍无横向溢出。
- 语音识别语言改为跟随界面语言（此前硬编码 zh-CN，英文界面也用中文识别）。

### 桌面端（M4）

- 重写 `xiaoman.spec`：清掉已删除的 mem0/chromadb/alembic/opentelemetry 引用，
  用文件系统递归收集 litellm 子模块 + 整目录收集其非 Python 资源
  （模型价格表、tokenizer）——缺任一项启动即失败，实测踩过。
- `run.py` 修数据目录：打包后默认 `~/.xiaoman`（此前文档这么写但代码没做）。
- 实测产出 144MB 单文件，启动后健康检查 200、前端完整渲染、写入落盘、MCP 200。

## [2.5.0] - 2026-10-20（家庭账本上界面 + 升级路径实证）

### 新增

- **家庭账本界面**（设置 → 家庭账本）：成员增删、成员间借贷（记录/结清/删除）、
  家庭收支汇总与各成员占比。这套后端能力（12 个端点）此前完全没有前端入口。
- **升级演练脚本** `backend/scripts/upgrade_drill.py`：用旧版 schema 造一个带数据的库，
  再用当前代码打开，验证 12 张表数据完整、复合主键共存、重复启动幂等、旧路径自动搬迁。
- e2e 新增家庭账本全流程（添加成员 → 汇总 → 借贷 → 结清）。

### 安全

- **迁移前自动整库备份**：多租户迁移会重建四张表（DROP + RENAME，无回滚点），
  现在动结构前先复制一份 `<db>.pre-mt-<时间戳>`。备份失败只告警不阻断，但一定留痕。
- 迁移幂等有测试兜底：已迁移的库再次启动不会再产生备份。

### 验证

- 升级演练 ALL PASSED（旧库 12 张表 → 迁移后条数一致）。
- 迁移备份实测：`.pre-mt-*` 文件内容为迁移前状态（无 user_id、数据完整）。

## [2.4.3] - 2026-10-20（溯源链上界面）

### 新增

- **溯源链界面**（设置 → 数据与安全 → 溯源链）：把后端已有的 `/api/provenance` 接到前端。
  可按实体类型与 ID 过滤，逐条展开查看改动前/后快照，回答"这个数字是谁在什么时候改的"。
  此前该能力只有接口、界面上完全看不到——而这正是产品宣称的"数字可对质"卖点。
- 接口测试 2 项：写入产生溯源记录、按类型过滤、单条详情 404。

## [2.4.2] - 2026-10-20（Docker 数据持久化修复 + 实测验证）

### 修复（P0）

- **容器重建丢账本**：代码默认把库写在 `backend/app/data`，而 Dockerfile 的 VOLUME 与
  compose 挂的是 `backend/data`。实测确认：容器内写入的数据落在卷外，`docker rm` 即丢。
  现在库 / 备份 / LangGraph checkpoint 统一由 `XIAOMAN_DATA_DIR` 决定（默认 `backend/data`），
  镜像内置 `/app/backend/data`，与数据卷一致。
- **旧数据自动迁移**：升级后首次启动若新位置无库、旧位置有库，自动搬移（连带 `-wal` / `-shm`，
  避免 WAL 中已提交事务丢失）。显式设置 `XIAOMAN_DB_PATH` 时不猜。
- **备份与 checkpoint 同目录**：`BACKUP_DIR` 与 `agent_checkpoints.db` 一并跟随数据目录，
  不再散落在代码目录里。

### 验证（本轮实际执行）

- Docker 实机构建 + 运行：健康检查 `healthy`、首页 200、`/mcp` 200、以 uid 1000 非 root 运行。
- 容器写入数据 → `docker rm` → 重建 → 数据仍在（此前会丢）。
- 部门工单白名单补端到端测试：模型实际收到的工具面被收窄到工单声明的那一个。

### 文档

- `docs/planning/` 九份规划文档统一加「归档说明」：标明记录的是当时决策过程，
  当前状态以 PROGRESS 与代码为准（文中 mem0/规则引擎/react_agent 等已移除）。
- PROGRESS 里程碑校准：M2 95%、M3 100%（白名单已生效）、M4 60%（Docker 已验证）。

## [2.4.1] - 2026-10-20（关键端点测试补全 + 性能与超时）

### 新增

- **关键端点 HTTP 测试**（10 项）：`/api/confirm` 的一次性 token 语义（重复确认必须 409、写操作只发生一次）、附件上传/删除/类型校验、审计与日志列表。

### 修复

- **收尾请求不再拖死整次问答**：工具轮次用尽后本应基于已有结果成文，但此前该请求无超时预算，网关抖动时会挂到 120s。现收紧到 20s（外层 25s 兜底），超时立即走确定性模板——实测网关 504 时 1.1 秒内给出降级回答。
- **LLM 客户端指纹包含 api_key**：此前只比对模型名与端点，用户在设置页换密钥后仍复用旧 client，表现为"改了 key 仍 401，重启才好"。现用密钥哈希前 8 位参与指纹。

### 性能

- **MCP 工具发现加 30s 缓存**：每次问答都重新握手并 list_tools，实测拉长首 token 时间。缓存键包含配置指纹，换配置立即失效。

### 清理

- 删除与 `manifest.webmanifest` 逐字节相同的 `manifest.json`，同步更新 Service Worker 预缓存清单。

## [2.4.0] - 2026-10-20（完整多租户 + 遗留缺陷收口）

> 定位：一个实例支持多个独立账本，且历史数据可平滑升级。

### 新增

- **完整多租户隔离**：业务表新增 `user_id` 维度，JWT 登录用户各自拥有独立数据。
  - 四类"业务字段作主键"的表（持仓 `symbol`、订阅/负债/目标 `name`、自选 `symbol`）改为 `(user_id, 原主键)` 复合主键——两人都持有「茅台」或都有「买房」目标时不再互相覆盖。
  - `sessions.thread_id` 的全局唯一约束改为 `(user_id, thread_id)`；`conversation_summary` 同理。
  - 所有读写按请求上下文中的租户过滤（`app/db/tenant.py` 的 ContextVar），未登录请求落在默认租户 0。
  - 备份/恢复按租户隔离：恢复只清当前用户的数据，绝不抹掉别人的账本。
  - 自动迁移：启动时检测旧库并就地升级（补列、重建复合主键表、回填历史数据到默认租户），幂等可重跑。
- **租户覆盖护栏**：`backend/scripts/check_tenant_coverage.py` 静态扫描数据层 SQL，任何漏加 `user_id` 的查询都会报错；确需跨租户的维护操作须显式标注 `# tenant: allow`。
- **隔离测试**：数据层 7 项 + HTTP 端到端 4 项（两个 JWT 用户的持仓/流水/目标互不可见）。

### 修复

- **健康分统一口径**：`analysis.health_check` 改用五维加权（与 `calculations/health.py` 一致），并补上 `grade` 字段（呈批件此前一直显示"得分 X（—）"）。
- **部门工单白名单生效**：执行阶段按 `order.tools_allowed` 收窄工具面，LLM 派工的"只给两个工具"约束不再是空话。
- **MCP 清仓接入审批**：`shares=0`（清仓）此前算成 0 元永不触发审批，现按持仓市值兜底，清仓这种最不可逆的操作必须确认。
- **测试并行稳定**：`test_evaluate` 的临时库 fixture 未先关闭旧连接，共享默认库时会串数据；补 `close_db()`。
- **测试 JWT 密钥固定**：避免每次导入生成随机 secret 导致同轮测试签发/校验不一致。

## [2.3.0] - 2026-10-20（可用性总修：工具链路、部署、响应式、跨平台）

> 定位：把"能跑"变成"跑对"。本轮以实际运行验证为准，修复了会让核心能力整体失效的缺陷。

### 修复（P0）

- **工具调用整体失效**：LiteLLM 1.106 在带 `tools` 时会导入其内置 MCP 网关，该模块依赖 mcp>=2 才有的 `CacheableResult`，而项目锁定 mcp 1.30（fastmcp 2.x 要求 <2.0）。表现为任何 function calling 直接 ImportError，模型永远拿不到工具。现在显式传 `_skip_mcp_handler=True` 绕开这条未使用的分支。
- **前端静态托管被遮蔽**：MCP 子应用曾 `Mount("/")`，拦截所有未匹配请求，单端口部署时 `/` 与 `/index.html` 返回 503。改为只挂 `/mcp`，并新增精确路径路由，使 `/mcp` 与 `/mcp/` 都直达（不再 307）。
- **`/mcp` 鉴权与来源校验**：改为复用主应用同一套判定（口令 + 本机/内网来源 + Host/Origin 白名单），消除"主站有防护、MCP 侧裸奔"的第二信任边界。
- **MCP 批量导入 100% 失败**：`mcp_server.py` 中 `from ..csvimport` 越界相对导入，改为 `from .csvimport`。
- **设置页无法保存**：`saveMutate` 从未被调用，月收入/应急目标/储蓄率/晨报时间只改本地 state。新增底部保存栏（含未保存提示与放弃改动）。
- **首屏 hooks 顺序违规**：`App.tsx` 在部分 hooks 之间条件 return 登录页，已注册实例且无 token 时会白屏。条件 return 移到全部 hooks 之后。
- **依赖不可解**：`langgraph` 与 `langchain-core<0.4` 约束互斥；移除重复的 `react_agent`（官方 ReAct 包装）后统一走 `agent.run_agent`，依赖树恢复可解。
- **Docker 数据路径退化**：compose 注入空串导致 `XIAOMAN_DB_PATH=""`，`Path("")` 解析为当前目录。路径解析改为忽略空值并展开相对路径；compose 不再传该变量。
- **`.env` 泄密路径**：一键脚本把含密钥的 `.env` 写到仓库根但未被忽略，现已在 `.gitignore` 覆盖根目录 `.env`。

### 修复（P1）

- **确认接口可重复执行**：新增 `claim_pending_action` 原子抢占（条件 UPDATE + rowcount 校验），并发/重放只有一方能执行；图内与降级路径都改用它。
- **成员删除外键失败**：改为先删 `member_loans` 再删 `members`，并包在事务里。
- **撤回流水外键失败**：`owner_id` 为空时保持 NULL，不再写成 0。
- **备份不完整**：导出/恢复补齐成员、借贷、自选、溯源、审计五类数据；流水恢复保留 `owner_id`/`is_shared`；格式版本升到 3（兼容读 v2）。
- **关闭晨报连带关掉订阅巡检**：两者解耦，巡检始终注册。
- **收益率口径**：简单收益率只把非工资性流入算作追加本金；XIRR 改为"成本投入 → 当前市值"两笔现金流，不再把生活收支混进投资收益。
- **附件上传必然 400**：前端不再对 FormData 强制注入 JSON Content-Type；后端校验 multipart 并拒绝 PDF（明确告知，而不是把二进制当文本）。
- **财务快照卡恒为空**：字段名修正为 `total_market_value`，储蓄率不再重复乘 100。
- **收件箱请求循环**：`markAllRead` 改用 ref 读取最新列表，回调身份稳定，不再触发 effect 反复请求。
- **Service Worker 永不更新**：构建脚本改为按内容哈希替换 `CACHE` 常量，并可幂等重跑。
- **行情下跌不显示跌幅**：涨跌额/涨跌幅改用允许负数的解析器。
- **`/api/health-check` 免鉴权**：从白名单移除（会输出财务体检结论）。
- **工具层设置键不一致**：补 `lang` 白名单，`morning_report_time` 归一为 `report_time` 并触发调度重排。

### 变更

- **长记忆改为纯本地**：移除 mem0 + chromadb（其 embedder 默认走 OpenAI，记忆内容会离开本机），改用本地 BM25 检索 `user_memory`，接口 `remember/recall` 不变。
- **删除未接线的规则引擎**：`rules.py` / `settings_rules.py` 全仓无调用，连同测试一并移除。
- **删除 11 个未使用 UI 组件与 7 个 Radix 依赖**。
- **可观测性改为零依赖**：移除 OpenTelemetry/Phoenix 依赖，改用标准库记录 LLM/工具耗时，`/api/metrics` 输出平均值/峰值/次数。
- **响应式**：侧栏与数据面板支持拖拽调宽（持久化、双击复位）；手机端新增底部导航；设置页在窄屏按三组折叠；数据面板在 xl 断点才挤占主区，消除 768–1279 的半遮挡；面板补齐焦点陷阱与焦点归还。
- **首屏体积**：Dashboard/部门面板/收件箱面板改为懒加载，主包 581KB → 453KB。

### 跨平台

- `scripts/dev.sh`、`scripts/lint.sh`、`scripts/e2e-backend.sh`、`deploy/one-click.sh` 自动探测 `Scripts/python.exe` 与 `bin/python`，Python 命令按 `python3 → python → py` 回退。
- `start.bat` 支持 `--prod`，自动建 venv 与装依赖；`.gitattributes` 固定 `.bat` 为 CRLF、`.sh` 为 LF。

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
