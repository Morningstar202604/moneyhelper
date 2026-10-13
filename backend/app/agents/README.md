# Agents 目录结构

2026 主流 agent 框架（Vercel Eve / Flue / Mastra）的文件驱动范式：
**每个 agent 是一个目录**，不是一堆单文件。

## 目录约定

```
agents/
├── supervisor/          # 总调度 agent（意图分类 + 路由）
│   ├── instructions.md  # 系统提示词（独立 markdown，好改好版本控制）
│   └── tools.py         # 这个 agent 专属工具（可选）
├── bookkeeping/         # 记账 agent
│   ├── instructions.md
│   └── tools.py
└── portfolio/           # 持仓行情 agent
    ├── instructions.md
    └── tools.py
```

## 为什么这样设计

1. **提示词独立成文件** —— 不用改 Python 代码就能调提示词，git diff 清晰
2. **工具按 agent 分组** —— 每个 agent 只看到自己该用的工具，减少 token 消耗
3. **技能按需加载** —— 未来可以加 `skills/` 目录，agent 遇到特定话题才加载对应知识

## 迁移进度

- [x] supervisor/instructions.md
- [x] bookkeeping/instructions.md
- [x] portfolio/instructions.md
- [ ] supervisor/tools.py（从 tools.py 拆分）
- [ ] bookkeeping/tools.py（从 tools.py 拆分）
- [ ] portfolio/tools.py（从 tools.py 拆分）

## 当前状态

现在所有工具还在 `app/tools.py` 一个文件里。
按 agent 拆分是渐进式迁移，不影响现有功能。
