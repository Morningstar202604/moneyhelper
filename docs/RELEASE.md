# 发版流程

## 版本号真源

版本号只有一个真源：`backend/app/version.py` 的 `__version__`。

派生关系：

| 位置 | 如何得到 |
|---|---|
| 后端 `app.__version__` | 导入 `app/version.py` |
| FastAPI 的 `version` 字段 | 同上（`/docs` 显示的就是它） |
| 前端界面显示 | 构建时由 `vite.config.ts` 读 `version.py` 注入 `__APP_VERSION__` |
| `pyproject.toml` | 发版脚本同步（打包工具需要静态值） |
| `frontend/package.json` | 发版脚本同步 |

历史说明：改造前三处版本号各自漂移（`app/__init__.py` 1.0.0、`package.json` 1.4.0、
`pyproject.toml` 2.1.0），用户问"这是什么版本"会得到不同答案。现在不会了。

## 发版步骤

```bash
# 1. 确认工作区干净、测试全绿
git status
cd backend && .venv/bin/python -m pytest tests -q && cd ..
cd frontend && npx vitest run && cd ..

# 2. 预演：看下一版号与 CHANGELOG 条目（不修改文件）
./scripts/release.sh --dry-run

# 3. 执行：改版本号 + 写 CHANGELOG + 提交 + 打 tag
./scripts/release.sh

# 4. 人工确认后推送（脚本不自动推，避免误推未审阅内容）
git push origin main --follow-tags

# 5. 其余四个平台同步（各自独立推送）
git push gitee main --follow-tags
git push gitcode main --follow-tags
git push github-morningstar main --follow-tags
git push github-x33834 main --follow-tags
```

第 4 步的 tag 推送会触发 `.github/workflows/release.yml`：
校验 tag 与 `version.py` 一致 → 从 CHANGELOG 提取说明 → 创建 GitHub Release
→ 同步 tag 到两个 GitHub 镜像。

## 版本号如何推导

从上次 tag 到 HEAD 的提交信息按 conventional commits 判定：

| 提交特征 | 升位 |
|---|---|
| 含 `BREAKING CHANGE` 或 `type!:` | major |
| 有 `feat:` | minor |
| 其余（fix/docs/refactor/chore…） | patch |

不做的事：脚本不读取 `package.json` 的历史版本，也不允许手工指定版本号——
版本必须能从提交历史推导出来，否则"为什么是 2.2.0"就没有依据。

## CHANGELOG 格式

遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，按类型分组：
新功能 / 修复 / 重构 / 性能 / 文档 / 其他。条目直接取提交标题，
所以**提交信息本身就是发布说明的原料**——写清楚改了什么、为什么改。

## 常见问题

**tag 与 version.py 不一致**
`release.yml` 会直接失败。这通常意味着有人手工打了 tag 却没改版本号，
或改了版本号但 tag 沿用旧的。删掉 tag 重新发：
`git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`

**CHANGELOG 条目为空**
说明自上次 tag 以来没有该类型提交。检查 `git log <last-tag>..HEAD --format=%s`。

**镜像站没有 Release**
镜像 job 若因 token 未配置而跳过，tag 仍会同步（如果 token 有值）。
GitHub Release 需要各自仓库的 workflow 才能创建，当前镜像只同步代码与 tag。
