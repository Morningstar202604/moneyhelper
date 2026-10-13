# 打包成 Windows EXE

小满可以打包成单个 EXE 文件，用户双击就能跑，不需要装 Python / Node。

## 打包步骤

### 1. 先 build 前端

```bash
cd frontend
npm install
npm run build
# 产物在 frontend/dist/
```

### 2. 安装打包工具

```bash
cd backend
pip install pyinstaller
```

### 3. 打包

```bash
pyinstaller xiaoman.spec
```

产物在 `dist/xiaoman.exe`。

### 4. 测试

双击 `dist/xiaoman.exe`，应该：
1. 弹出控制台窗口显示日志
2. 自动打开浏览器到 http://127.0.0.1:8788
3. 关掉控制台窗口就停服务

## 数据目录

用户数据存在 `~/.xiaoman/`：
- SQLite 数据库
- 加密备份
- 配置文件

EXE 本身不存数据，删了 EXE 不影响用户数据。

## 注意事项

- EXE 大概 200-300MB（包含 Python 运行时 + 所有依赖）
- 第一次启动慢一点（要解压临时文件）
- Windows Defender 可能误报，加白名单就行
- 控制台窗口可以改成 GUI 模式（spec 里 `console=False`）
