@echo off
chcp 65001 >nul
setlocal
title 小满 · 一键启动
cd /d "%~dp0"

echo ============================================
echo    小满 Xiaoman  ·  一键启动
echo    后端  http://127.0.0.1:8788
echo    前端  http://127.0.0.1:5198
echo ============================================
echo.

rem 依赖检查（首次已装好则直接跳过）
if not exist "backend\.venv\Scripts\python.exe" (
  echo [错误] 后端虚拟环境缺失，请先执行：
  echo        cd backend ^&^& python -m venv .venv
  echo        cd backend ^&^& .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo [错误] 前端依赖缺失，请先执行：
  echo        cd frontend ^&^& npm install
  echo.
  pause
  exit /b 1
)

echo 正在启动后端（8788）...
start "小满后端-8788" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8788"

timeout /t 3 /nobreak >nul

echo 正在启动前端（5198）...
start "小满前端-5198" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 6 /nobreak >nul

echo 正在打开浏览器...
start "" http://127.0.0.1:5198/

echo.
echo 已启动完成。
echo   - 请保持那两个黑色控制台窗口运行（关掉其中一个即对应服务停止）。
echo   - 若浏览器没自动打开，请手动访问 http://127.0.0.1:5198
echo   - 停止服务：直接关闭两个控制台窗口即可。
echo   - 使用专用端口 8788/5198，可避开其他 AI 工具抢占端口导致的冲突。
echo.
pause
endlocal