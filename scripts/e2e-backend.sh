#!/usr/bin/env bash
# 后端 e2e 启动脚本：把数据库指向 backend/data/e2e.db，由 Playwright webServer 调用。
# 测试库每次跑都被 globalSetup 重新种入演示数据（见 frontend/e2e/global-setup.ts），
# 保证测试可重复；研发者日常 wealth.db 不受影响。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"

# 优先用项目 venv；缺则回退到系统 python（未装 requirements 时给明白的提示）
if [ -f "$BACKEND/.venv/bin/python3" ]; then
  PY="$BACKEND/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "[e2e] 未找到 python3，请安装 Python 3.10+" >&2
  exit 7
fi

if ! "$PY" -c "import uvicorn" 2>/dev/null; then
  echo "[e2e] uvicorn 未安装，请先在 backend 执行: $PY -m pip install -r requirements.txt" >&2
  exit 7
fi

cd "$BACKEND"
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8788
