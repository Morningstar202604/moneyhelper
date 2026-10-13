"""小满 EXE 入口：双击启动后端 + 自动打开浏览器。

打包后用户双击 xiaoman.exe：
1. 启动 FastAPI 后端（127.0.0.1:8788）
2. 自动打开默认浏览器
3. 控制台窗口显示日志，关掉窗口就停服务
"""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# 确保 app 目录在 path 里
sys.path.insert(0, str(Path(__file__).parent))

from app.main import app  # noqa: E402
import uvicorn  # noqa: E402


def open_browser_later(delay: float = 1.5):
    """延迟几秒后打开浏览器，等后端起来。"""
    def _open():
        time.sleep(delay)
        webbrowser.open("http://127.0.0.1:8788")
    threading.Thread(target=_open, daemon=True).start()


def main():
    port = int(os.getenv("PORT", "8788"))
    host = "127.0.0.1"

    print("=" * 50)
    print("  小满 — 对话优先的个人理财 Agent")
    print("=" * 50)
    print(f"  地址：http://{host}:{port}")
    print(f"  数据目录：{Path.home() / '.xiaoman'}")
    print("=" * 50)
    print("  按 Ctrl+C 或关掉窗口退出")
    print()

    # 自动打开浏览器
    open_browser_later()

    # 启动后端
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
