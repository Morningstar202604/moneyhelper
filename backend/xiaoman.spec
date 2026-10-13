# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：小满 v2 单文件 EXE。

用法：
    cd backend
    pyinstaller xiaoman.spec

产物：
    dist/xiaoman.exe —— 双击就能跑，自动启动后端 + 打开浏览器
"""

import os
import sys
from pathlib import Path

block_cipher = None

# 前端静态文件目录（build 后的 dist）
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 前端静态文件嵌入 EXE
        (str(FRONTEND_DIST), 'static'),
        # agents 配置文件
        ('app/agents', 'app/agents'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # LiteLLM
        'litellm',
        # LangGraph
        'langgraph',
        # mem0
        'mem0',
        # chromadb
        'chromadb',
        # OpenTelemetry
        'opentelemetry',
        'opentelemetry.sdk',
        'opentelemetry.exporter',
        'opentelemetry.exporter.otlp',
        'opentelemetry.exporter.otlp.proto',
        'opentelemetry.exporter.otlp.proto.http',
        # FastAPI
        'fastapi',
        'sse_starlette',
        # SQLite
        'aiosqlite',
        # APScheduler
        'apscheduler',
        # Alembic
        'alembic',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='xiaoman',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 设 False 就不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以加个 .ico 文件
)
