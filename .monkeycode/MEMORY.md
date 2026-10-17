# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries

[Multi-Platform Git Sync - xiaoman]
- Date: 2026-10-18
- Context: 用户提供了 5 个代码托管平台凭据，要求克隆 xiaoman 项目并后续在 5 平台推送
- Category: Workflow & Collaboration
- Instructions:
  - xiaoman 项目同步在 5 个平台，开发后的推送需覆盖全部远程：
    - gitcode: https://gitcode.com/badhope/xiaoman.git (账号 badhopel)
    - gitee: https://gitee.com/badhope/xiaoman.git (账号 badhope)
    - github-morningstar: https://github.com/Morningstar202604/xiaoman.git
    - github-badhope: https://github.com/badhope/xiaoman.git
    - github-x33834: https://github.com/X33834/xiaoman.git
  - 凭据已存入 /root/.git-platform-env（环境变量）、/root/.git-credentials（credential store）、/root/.netrc，权限 600
  - 注意：x33834 与 badhope 两个 GitHub 账号的 token 已失效（401），公开仓库可读但推送会失败；有效 token 为 Morningstar202604 的
  - 推送避坑（2026-10-18 实测）：
    - 环境注入的 credential helper（/app/agent/bin/agent git-credential-helper）对 GitHub 返回 500，GitHub 推送需用显式凭据 URL：git push "https://x-access-token:${GITHUB_TOKEN_MORNINGSTAR}@github.com/Morningstar202604/xiaoman.git" main（token 不回显到输出）
    - gitee/gitcode 用远程名正常推送
    - 重新克隆后远程名只有 origin，需重建：rename origin→gitee，add gitcode/github-morningstar/github-badhope/github-x33834；scripts/push-all.sh 里的远程名与实际拓扑已不符，勿直接使用
  - 2026-10-18 探测时 4 个平台同步在 ad8ce8a，仅 GitHub/X33834 落后在 fb06e72；克隆源为 gitee
  - 项目主目录：/workspace/xiaoman，推送时用 `git push <remote> main` 逐个推送

[Xiaoman 项目概况]
- Date: 2026-10-18
- Context: 克隆项目后阅读 README 了解项目定位
- Category: Environment Configuration
- Instructions:
  - 小满（xiaoman）：对话式个人财务助手，MIT 协议
  - 技术栈：backend = Python FastAPI + LangGraph 多 Agent（supervisor/bookkeeping/portfolio）+ SQLite 本地存储 + LiteLLM 多模型接入 + MCP Server（fastmcp）；frontend = React 19 + Vite + shadcn/ui + TanStack Table
  - 关键特性：数据 100% 本地、确定性引擎算账（模型只分类不碰数字）、SSE 流式、PWA、Arize Phoenix 可观测、mem0 记忆
  - 文档集中在 docs/（ARCHITECTURE-v2.md、PLAN-DETAILED.md、ROADMAP-v3.md 等）
