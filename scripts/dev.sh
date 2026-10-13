#!/usr/bin/env bash
# 小满 · 一键开发启动（后端 8788 + 前端 dev 5198，Ctrl-C 一起退出）。
# 用专用端口 8788/5198，避开其他工具抢占 8787/5199 导致的端口冲突。
# 用法：scripts/dev.sh    （在仓库根目录执行；会按需创建 venv / 安装依赖）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

command -v python3 >/dev/null 2>&1 || { echo "✗ 缺少 python3（需 3.9+，建议 3.12）"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "✗ 缺少 node（需 18+）"; exit 1; }

# 端口占用预检：避免旧进程残留导致 uvicorn/vite 静默绑定失败
_port_free() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -i ":$port" -sTCP:LISTEN -t 2>/dev/null && return 1
  elif command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" 2>/dev/null | grep -q ":$port" && return 1
  fi
  return 0
}
for _p in 8788 5198; do
  if ! _port_free "$_p"; then
    echo "✗ 端口 $_p 已被占用（lsof -i :$_p 查看占用方），请先释放后重试"
    exit 1
  fi
done

# 后端：venv + 依赖
if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  echo "== 创建后端虚拟环境 =="
  python3 -m venv "$BACKEND/.venv"
fi
if ! "$BACKEND/.venv/bin/python" -c "import fastapi, uvicorn, aiosqlite" >/dev/null 2>&1; then
  echo "== 安装后端依赖 =="
  "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi

# 前端：依赖
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "== 安装前端依赖 =="
  (cd "$FRONTEND" && npm install --no-audit --no-fund)
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "== 启动后端 http://127.0.0.1:8788 =="
(cd "$BACKEND" && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8788) &
echo "== 启动前端 dev http://127.0.0.1:5198 =="
(cd "$FRONTEND" && npm run dev) &
wait
