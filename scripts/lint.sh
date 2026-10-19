#!/usr/bin/env bash
# 全仓库静态检查：与 CI 完全同一套命令，避免"本地过了 CI 挂"。
# CI 查 app/tests 与 xiaoman 两处；本地只跑一处就会漏（历史上漏过一次）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"

fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }

[ -x "$PY" ] || fail "找不到 backend/.venv/bin/python"

cd "$ROOT/backend"
"$PY" -m ruff check app tests || fail "ruff: backend/app + tests"
ok "ruff: backend/app + tests"

cd "$ROOT"
"$PY" -m ruff check xiaoman || fail "ruff: xiaoman 分层包"
ok "ruff: xiaoman 分层包"
