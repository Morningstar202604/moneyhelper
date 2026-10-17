#!/bin/bash
# 本地一键三仓推送：主仓 origin(GitHub badhope) + GitCode + Gitee（均为 badhope，用户指定拓扑）
# 用法: ./scripts/push-all.sh [commit-message]
set -e
cd "$(dirname "$0")/.."
if [ -n "$1" ]; then git add -A && git commit -m "$1"; fi
echo "── origin (github/badhope) ──"; git push origin main --follow-tags
echo "── gitcode ──";              git push gitcode-mirror main --force --follow-tags
echo "── gitee ──";                git push gitee main --force --follow-tags
echo "✅ badhope 三仓同步完成"
