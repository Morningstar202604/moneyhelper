#!/bin/bash
# 本地一键五仓推送：主仓 origin(GitHub badhope) + 4 镜像
# 用法: ./scripts/push-all.sh [commit-message]
set -e
cd "$(dirname "$0")/.."
source ~/.bashrc 2>/dev/null || true
if [ -n "$1" ]; then git add -A && git commit -m "$1"; fi
echo "── origin (github/badhope) ──"; git push origin main --follow-tags
echo "── gitee ──";                git push gitee main --force --follow-tags
echo "── gitcode ──";              git push gitcode-mirror main --force --follow-tags
echo "── morningstar ──";         git push gh-morningstar main --force --follow-tags
echo "── x33834 ──";              git push gh-x33834 main --force --follow-tags
echo "✅ 五仓同步完成"
