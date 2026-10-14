"""FastAPI 入口：REST + SSE 流式问答 + 最小鉴权 + 静态前端托管。

鉴权：设置 API_TOKEN 后，所有 /api/* 需带 `Authorization: Bearer <口令>`
或查询参数 `?token=<口令>`；未设置则仅限本机/内网使用。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import Coroutine
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import (
    analysis,
    auth,
    backup,
    db,
    evaluate,
    llm,
    quotes,
    scheduler,
    service,
    vault,
)
from .auth import verify_api_token
from .logging_utils import clear_logs, read_log_lines
from .logging_utils import get_logger as _get_logger
from .quotes import invalidate_quotes_cache

# HITL 确认 per-token 并发锁上限：与 agent_graph._HITL_THREADS 共用同一常量，
# 防止单用户/攻击者用大量挂起 token 耗尽内存。
_CONCURRENT_HITS_MAX = 512
_confirm_locks: OrderedDict[str, asyncio.Lock] = OrderedDict()

log = _get_logger(__name__)

# 轻量观测：进程启动时刻 + 累计请求/错误计数（/api/metrics 输出 Prometheus 文本格式）
_START_TS = time.monotonic()
_METRICS = {"requests": 0, "errors": 0, "auth_401": 0, "messages": 0}

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent.parent  # 仓库根目录
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app_ref: FastAPI):
    log.info("xiaoman backend starting up")
    await db.init_db()
    # vault 初始化：从环境变量取主口令（可选；未设则 ai_api_key 将拒绝加密存储）
    vault_pass = os.getenv("VAULT_PASSPHRASE", "").strip()
    if vault_pass:
        try:
            vault.init_master_passphrase(vault_pass)
            vault.activate()
            log.info("vault initialized")
        except Exception as e:
            log.warning("vault init failed: %s — ai_api_key 将拒绝加密存储", e)
    # JWT secret 弱默认值告警
    auth.check_jwt_secret()
    # 首次启动无用户时，从环境变量创建管理员（可选）
    await _maybe_create_admin()
    await scheduler.start()
    # Langfuse 观测：懒初始化（没配 env 就 no-op）
    from . import observability
    observability._init()
    # Agent 配置：初始化默认角色/skills/工具配置
    from . import agent_config
    await agent_config.init_default_config()
    log.info("database initialised, scheduler started")
    yield
    log.info("xiaoman backend shutting down")
    await scheduler.stop()
    await llm.aclose()
    vault.reset_cache()
    await db.close_db()
    # Langfuse flush：把缓存的 trace 刷出去
    observability.flush()
    log.info("xiaoman backend shutdown complete")
    # 关闭 agent HITL 进程内注册表持有的磁盘连接（同步 sqlite3，需在 loop 关闭前清理）
    from .agent_graph import close_checkpoints
    await close_checkpoints()



# ---------------------------------------------------------------------------
# FastAPI 实例（必须在所有 @app.* 路由/中间件/异常处理器之前）
# ---------------------------------------------------------------------------
app = FastAPI(title="小满 API", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# 全局异常兜底：所有未捕获异常都写进日志文件，方便事后诊断
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("unhandled exception in %s %s", request.method, request.url.path)
    # 不回吐异常细节（避免泄露 SQL/路径/内部模块），细节只进日志
    return JSONResponse({"error": "内部错误，请查看服务日志"}, status_code=500)


# ---------------------------------------------------------------------------
# 限流：in-memory 滑动窗口，按 IP 计数；单进程部署；多进程需换 Redis。
# ---------------------------------------------------------------------------
_RATE_LIMIT_ENABLED = not os.getenv("XIAOMAN_DISABLE_RATE_LIMIT")
_RATE_LIMIT_MAX = 200       # 单 IP 每分钟上限
_RATE_LIMIT_WINDOW = 60.0   # 窗口大小（秒）
_rate_buckets: dict[str, list[float]] = {}
# 跳过鉴权/限流的内部端点（health/health-check/metrics）统一枚举，避免三处不一致
_SKIP_AUTH_PATHS = {"/api/health", "/api/health-check", "/api/metrics",
                     "/api/auth/login", "/api/auth/register", "/api/auth/user-count"}


def _rate_limit_check(client_ip: str) -> tuple[bool, int]:
    """返回 (是否放行, 0=放行 or 秒数=retry_after)。"""
    if not _RATE_LIMIT_ENABLED:
        return True, 0
    now = time.time()
    bucket = _rate_buckets.setdefault(client_ip, [])
    cutoff = now - _RATE_LIMIT_WINDOW
    _rate_buckets[client_ip] = [t for t in bucket if t > cutoff]
    bucket = _rate_buckets[client_ip]
    if not bucket:
        # 旧 IP 离开窗口后条目仍在 dict 里——及时清掉，防长期运行的无限膨胀
        _rate_buckets.pop(client_ip, None)
        return True, 0
    if len(bucket) >= _RATE_LIMIT_MAX:
        retry_after = int(bucket[0] + _RATE_LIMIT_WINDOW - now) + 1
        return False, max(1, retry_after)
    bucket.append(now)
    return True, 0


@app.middleware("http")
async def rate_limiter_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in _SKIP_AUTH_PATHS:
        client = request.client
        ip = client.host if client else "127.0.0.1"
        ok, retry_after = _rate_limit_check(ip)
        if not ok:
            return JSONResponse(
                {"error": "请求过于频繁，请稍后再试"},
                status_code=429,
                headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(_RATE_LIMIT_MAX)},
            )
    return await call_next(request)

# fire-and-forget 后台任务持有集：防止 create_task 返回的 Task 在完成前被 GC
# 取消（asyncio 只保留弱引用，无人持引用时任务可能静默失效）。
_background_tasks: set[asyncio.Task[None]] = set()


def _spawn_background(coro: Coroutine[Any, Any, None]) -> None:
    """登记后台任务并自动在完成时移除引用；登记失败不影响主流程。"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


_dev_origins = {"http://127.0.0.1:5198", "http://localhost:5198"}
if os.getenv("CORS_ALLOW_ALL") == "1":  # 仅调试用
    _dev_origins = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_dev_origins) if _dev_origins is not None else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 最小鉴权：API_TOKEN 未设置 = 开放（仅限本机/内网）；设置后所有 /api/* 需带口令
# ---------------------------------------------------------------------------


@app.middleware("http")
async def api_auth(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in _SKIP_AUTH_PATHS:
        key = os.getenv("API_TOKEN", "").strip()
        # 鉴权逻辑共用 auth.verify_api_token（_timing-safe 比对_）
        if key and verify_api_token(request) is None:
            return JSONResponse({"error": "需要访问口令"}, status_code=401)
    return await call_next(request)


# ---------------------------------------------------------------------------
# 无口令模式的 Host/Origin 防护（DNS rebinding / 跨站读取）：
# 未设 API_TOKEN 时仅放行本机与 ALLOWED_HOSTS 白名单；/api/health 恒免检；
# 设了口令则以口令为准（反代部署不拦截）。注册在 api_auth 之后 = 更外层。
# ---------------------------------------------------------------------------

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "testserver"}


def _hostname(value: str) -> str:
    """剥离端口的主机名（支持 host:port 与 [v6]:port）。"""
    v = (value or "").strip().lower()
    if v.startswith("["):
        return v.split("]", 1)[0] + "]"
    return v.rsplit(":", 1)[0] if v.count(":") == 1 else v


def _allowed_hosts() -> set[str]:
    extra = {
        h.strip().lower()
        for h in os.getenv("ALLOWED_HOSTS", "").split(",")
        if h.strip()
    }
    return _LOCAL_HOSTS | extra


def _host_allowed(host: str, allowed: set[str]) -> bool:
    """ALLOWED_HOSTS 含 * 时放行所有主机名（预览域名等不可枚举的场景）。"""
    if "*" in allowed:
        return True
    return host in allowed


@app.middleware("http")
async def host_guard(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith("/api/")
        and path not in _SKIP_AUTH_PATHS
        and not os.getenv("API_TOKEN", "").strip()
    ):
        allowed = _allowed_hosts()
        host = _hostname(request.headers.get("host", ""))
        if host and not _host_allowed(host, allowed):
            return JSONResponse(
                {
                    "error": "不允许的 Host：未设置 API_TOKEN 时仅限本机/内网访问，"
                    "如需按主机名部署请设置 ALLOWED_HOSTS 或 API_TOKEN"
                },
                status_code=403,
            )
        origin = request.headers.get("origin", "")
        if origin:
            oh = (urlsplit(origin).hostname or "").lower()
            if oh and not _host_allowed(oh, allowed) and oh != host:
                return JSONResponse({"error": "不允许的 Origin"}, status_code=403)
    return await call_next(request)


# ---------------------------------------------------------------------------
# 安全响应头：所有响应统一加固（防 MIME 嗅探 / 点击劫持 / 敏感来源泄露）
# 用 setdefault 避免覆盖下游主动设置；不设 CSP，避免破坏 Vite 内联 module 与 echarts。
# ---------------------------------------------------------------------------


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # 本机语音输入用麦克风（voice_input），故保留 microphone；其余能力收紧
    resp.headers.setdefault(
        "Permissions-Policy",
        "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)",
    )
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return resp


async def _maybe_create_admin() -> None:
    """首次启动（零用户时）从环境变量创建管理员账号。
    变量：ADMIN_USERNAME / ADMIN_PASSWORD（同时设置才生效）。"""
    if await db.user_count() > 0:
        return
    username = os.getenv("ADMIN_USERNAME", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    if username and password:
        try:
            uid = await db.user_create(username, password, display_name=username, role="admin")
            log.info("Initial admin created: id=%d username=%s", uid, username)
        except Exception as e:
            log.warning("Admin creation failed: %s", e)


# ---------------------------------------------------------------------------
# 用户认证（JWT + bcrypt）
# ---------------------------------------------------------------------------


@app.post("/api/auth/register")
async def api_register(req: auth.RegisterReq):
    return await auth.register(req)


@app.post("/api/auth/login")
async def api_login(req: auth.LoginReq, request: Request):
    return await auth.login(req, request)


@app.get("/api/auth/me")
async def api_me(user: dict = Depends(auth.require_user)):
    return await auth.me(user)


@app.get("/api/auth/user-count")
async def api_user_count():
    return {"count": await db.user_count()}


# ---------------------------------------------------------------------------
# 健康 / 引导 / 仪表盘
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "llm_configured": await llm.llm_available(),
        "model": await _llm_model(),
    }


# ---------------------------------------------------------------------------
# 轻量观测：请求计数 / 错误 / 运行时长（Prometheus 文本格式，可直接被采集器抓取）
# ---------------------------------------------------------------------------


@app.middleware("http")
async def _metrics_counter(request: Request, call_next):
    _METRICS["requests"] += 1
    resp = await call_next(request)
    if resp.status_code >= 500:
        _METRICS["errors"] += 1
    elif resp.status_code == 401:
        _METRICS["auth_401"] += 1
    return resp


# 审计日志（P2 金融级治理）：记录写操作与敏感读，便于追溯。
# - 写类（非 GET /api/*）：统一审计，排除健康/指标/审计自身等低敏或自引用路径；
# - 敏感读（导出、设置、备份相关）：单独标记 READ_SENSITIVE；
# - 触发鉴权（401/403）：标记 AUTH。
AUDIT_SKIP_PREFIXES = (
    "/api/health",
    "/api/metrics",
    "/api/audit",
    "/api/bootstrap",
    "/api/dashboard",
    "/api/quotes",
    "/api/market",
    "/api/kline",
    "/api/reports",
)
AUDIT_SENSITIVE_READ = ("/api/export", "/api/settings", "/api/reflections")


@app.middleware("http")
async def _audit_logger(request: Request, call_next):
    started = time.monotonic()
    path = request.url.path
    method = request.method
    resp = await call_next(request)
    if not path.startswith("/api/"):
        return resp
    duration_ms = int((time.monotonic() - started) * 1000)
    try:
        actor = (request.client.host if request.client else "") or ""
        action = None
        # 敏感读：导出/设置/口令
        if method == "GET" and path in AUDIT_SENSITIVE_READ:
            action = "READ_SENSITIVE"
        elif method != "GET" and not path.startswith(AUDIT_SKIP_PREFIXES):
            action = "WRITE"
        elif resp.status_code == 401:
            action = "AUTH"
        if action:
            await db.add_audit_log(
                action=action,
                method=method,
                path=path,
                status=resp.status_code,
                actor=actor,
                detail=f"{method} {path}",
                duration_ms=duration_ms,
            )
    except Exception:  # noqa: BLE001 — 审计失败不影响请求
        pass
    return resp


@app.get("/api/metrics")
async def metrics():
    body = "\n".join(
        [
            "# TYPE xiaoman_requests_total counter",
            f"xiaoman_requests_total {_METRICS['requests']}",
            "# TYPE xiaoman_errors_total counter",
            f"xiaoman_errors_total {_METRICS['errors']}",
            "# TYPE xiaoman_auth_401_total counter",
            f"xiaoman_auth_401_total {_METRICS['auth_401']}",
            "# TYPE xiaoman_messages_total counter",
            f"xiaoman_messages_total {_METRICS['messages']}",
            "# TYPE xiaoman_uptime_seconds gauge",
            f"xiaoman_uptime_seconds {time.monotonic() - _START_TS:.1f}",
            "",
        ]
    )
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


async def _llm_model() -> str:
    try:
        s = await db.get_settings()
        return (s.get("ai_model") or "").strip() or os.getenv("LLM_MODEL", "")
    except Exception:  # noqa: BLE001
        return os.getenv("LLM_MODEL", "")


def _mask_secret(settings: dict[str, str]) -> dict[str, str]:
    """对外返回时脱敏 AI Key：只回传"是否已配置"，绝不回传明文（与备份/导出策略一致）。"""
    if settings.get("ai_api_key"):
        settings["ai_api_key"] = "********"
    return settings


# ---------------------------------------------------------------------------
# 模块化路由：预算 / 目标 / 负债 / 订阅 / 行情 → backend/app/routes/
# ---------------------------------------------------------------------------

from .routes import (  # noqa: E402 — 就近放在挂载点导入，路由模块与主应用解耦
    budgets_router,
    calculations_router,
    debts_subs_router,
    family_router,
    goals_router,
    import_router,
    market_router,
    members_router,
    provenance_router,
)

app.include_router(budgets_router)
app.include_router(goals_router)
app.include_router(debts_subs_router)
app.include_router(market_router)
app.include_router(calculations_router)
app.include_router(import_router)
app.include_router(provenance_router)
app.include_router(members_router)
app.include_router(family_router)


@app.get("/api/bootstrap")
async def bootstrap() -> dict:
    settings = await db.get_settings()
    _mask_secret(settings)
    return {
        "settings": settings,
        "scheduler": scheduler.status(),
        "health": {
            "llm_configured": await llm.llm_available(),
            "model": await _llm_model(),
        },
        # 模型点亮（P0）：目录 + 已点亮清单，前端据此渲染输入区快捷切换与设置页勾选
        "model_catalog": llm.model_catalog(),
        "enabled_models": _enabled_model_list(settings),
    }


def _enabled_model_list(settings: dict[str, str]) -> list[str]:
    """把设置里的逗号分隔模型串解析成列表（只留目录内合法项，供前端用）。"""
    raw = str(settings.get("enabled_models") or "").strip()
    if not raw:
        return llm.default_enabled_models()
    catalog = {m["model"] for m in llm.model_catalog()}
    return [x for x in (s.strip() for s in raw.split(",")) if x and x in catalog]


@app.get("/api/dashboard")
async def dashboard(lang: str = "zh") -> dict:
    # lang 仅影响 flags/来源标签等展示文案的语言，不增加任何查询/往返开销
    return await analysis.collect_dashboard(lang=lang or "zh")


# ---------------------------------------------------------------------------
# 数据录入（持仓 / 流水 / 负债）
# ---------------------------------------------------------------------------


@app.post("/api/positions")
async def create_position(payload: dict) -> dict:
    try:
        out = await db.add_position(payload or {})
    except Exception as exc:  # noqa: BLE001 — 坏输入回 400
        return JSONResponse({"error": str(exc)}, status_code=400)
    await invalidate_quotes_cache()
    return out


@app.delete("/api/positions/{symbol}")
async def remove_position(symbol: str) -> dict:
    out = await db.delete_position(symbol)
    await invalidate_quotes_cache()
    return out


@app.put("/api/positions/{symbol}")
async def update_position(symbol: str, payload: dict) -> dict:
    try:
        out = await db.update_position(payload or {}, symbol)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)
    await invalidate_quotes_cache()
    return out


@app.post("/api/positions/merge")
async def merge_positions(payload: dict) -> dict:
    name = str((payload or {}).get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name 必填：要合并的持仓名称"}, status_code=400)
    try:
        out = await db.merge_positions_by_name(name)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)
    await invalidate_quotes_cache()
    return out


@app.post("/api/transactions")
async def create_transaction(payload: dict) -> dict:
    date = str(payload.get("date") or "").strip()
    item = str(payload.get("item") or "").strip()
    category = str(payload.get("category") or "其他").strip() or "其他"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return JSONResponse({"error": "日期需为 YYYY-MM-DD 格式"}, status_code=400)
    if not item:
        return JSONResponse({"error": "名称必填"}, status_code=400)
    try:
        amount = float(payload.get("amount", 0) or 0)
    except (TypeError, ValueError):
        return JSONResponse({"error": "金额不合法"}, status_code=400)
    if amount == 0:
        return JSONResponse({"error": "金额不能为 0"}, status_code=400)
    # owner_id 显式传入 or 自动取活跃成员
    owner_id = payload.get("owner_id")
    if owner_id is not None:
        try:
            owner_id = int(owner_id)
        except (TypeError, ValueError):
            return JSONResponse({"error": "owner_id 必须为整数"}, status_code=400)
    is_shared = payload.get("is_shared")
    try:
        return await db.add_transaction(
            date, item, category, amount,
            owner_id=owner_id,
            is_shared=is_shared,
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/transactions")
async def get_transactions(member_id: int | None = None) -> dict:
    """查询交易流水。member_id 有值时按家庭可见性过滤（shared=1 OR owner=自己）。"""
    rows = await db.list_transactions(member_id=member_id)
    return {"transactions": rows, "count": len(rows)}


@app.delete("/api/transactions/{tx_id}")
async def remove_transaction(tx_id: int) -> dict:
    return await db.delete_transaction(tx_id)


@app.put("/api/transactions/{tx_id}")
async def update_transaction(tx_id: int, payload: dict) -> dict:
    p = payload or {}
    owner_id = p.get("owner_id")
    if owner_id is not None:
        try:
            owner_id = int(owner_id)
        except (TypeError, ValueError):
            return JSONResponse({"error": "owner_id 必须为整数"}, status_code=400)
    is_shared = p.get("is_shared")
    try:
        return await db.update_transaction(
            tx_id,
            date=p.get("date"),
            item=p.get("item"),
            category=p.get("category"),
            amount=p.get("amount"),
            owner_id=owner_id,
            is_shared=is_shared,
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/transactions/merge")
async def merge_transactions(payload: dict) -> dict:
    p = payload or {}
    month = str(p.get("month") or "").strip()
    if not month:
        return JSONResponse({"error": "month 必填，格式 YYYY-MM"}, status_code=400)
    try:
        out = await db.merge_transactions(month, p.get("category"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)
    await invalidate_quotes_cache()
    return out


@app.post("/api/positions/{symbol}/append")
async def append_position(symbol: str, payload: dict) -> dict:
    """追加持仓：已有 symbol 则股数累加、成本加权平均（不覆盖），用于「合并」语义。"""
    from . import tools as _tools
    p = payload or {}
    async with _tools._position_write_lock:
        rows = await db.list_positions()
        cur = next((r for r in rows if r["symbol"] == symbol), None)
        if cur is None:
            return JSONResponse(
                {"error": f"持仓 {symbol} 不存在，请先添加"}, status_code=404
            )
        add_shares = float(p.get("shares") or 0)
        add_cost = float(p.get("cost") or 0)
        if add_shares <= 0:
            return JSONResponse({"error": "追加股数需大于 0"}, status_code=400)
        old_shares = cur["shares"]
        old_cost = cur["cost"]
        total = old_shares + add_shares
        avg_cost = (
            (old_shares * old_cost + add_shares * add_cost) / total
            if total > 0
            else old_cost
        )
        out = await db.update_position(
            {
                **cur,
                "shares": total,
                "cost": round(avg_cost, 6),
                "last": float(p.get("last", cur["last"])),
            },
            symbol,
        )
        await invalidate_quotes_cache()
        return {**out, "appended": True, "new_shares": total}


@app.post("/api/nl-add")
async def nl_add(payload: dict) -> dict:
    """一句话记账：规则解析优先（秒回），规则拿不到金额时升级 AI，AI 也失败则 422 提示。"""
    from . import nlparse

    text = str((payload or {}).get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "请输入一句话记账内容"}, status_code=400)

    parsed = nlparse.parse(text)
    source = "rule"
    if parsed is None:
        # 规则拿不到金额 → AI 兜底
        parsed = await nlparse.parse_with_ai(text)
        source = "ai" if parsed else None
    elif parsed["category"] == "其他" and parsed["amount"] < 0:
        # 规则拿到金额但分类不明确（非收入）→ AI 补分类，失败仍用规则结果入账
        ai = await nlparse.parse_with_ai(text)
        if ai is not None:
            parsed, source = ai, "ai"
    if parsed is None:
        return JSONResponse(
            {
                "error": "没读懂这句话，试试「昨天打车 32 元」「工资 8000 已到账」这样的说法"
            },
            status_code=422,
        )
    try:
        ins = await db.add_transaction(
            parsed["date"], parsed["item"], parsed["category"], parsed["amount"]
        )
        rows = await db.fetch_all("SELECT * FROM transactions WHERE id=?", (ins["id"],))
        tx = rows[0] if rows else {"id": ins["id"], **parsed}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, "source": source, "transaction": tx}


# ---------------------------------------------------------------------------
# 账单导入（CSV）
# ---------------------------------------------------------------------------


@app.post("/api/import/csv")
async def import_csv_parse(payload: dict) -> dict:
    """解析 CSV → 识别列映射 + 预览（前 15 条）+ 可导入条数统计。"""
    from . import csvimport

    content = str((payload or {}).get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "请粘贴账单 CSV 内容"}, status_code=400)
    try:
        parsed = csvimport.parse_csv(content)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    mapping = csvimport.detect_mapping(parsed["columns"])
    if mapping["amount"] < 0 or mapping["date"] < 0:
        return JSONResponse(
            {"error": "没能识别出日期/金额列，请确认表头包含「日期」「金额」等关键词"},
            status_code=422,
        )
    year = datetime.now().astimezone().strftime("%Y-%m")
    rows, skips = csvimport.build_rows(
        mapping, parsed["columns"], parsed["rows"], year_fill=year
    )
    return {
        "ok": True,
        "columns": parsed["columns"],
        "mapping": mapping,
        "preview": rows[:15],
        "rows": rows,
        "total": len(rows),
        "skipped": len(skips),
    }


@app.post("/api/import/commit")
async def import_csv_commit(payload: dict) -> dict:
    """按前端确认的 rows 批量入账；先全部校验通过再逐个入账。"""
    rows = (payload or {}).get("rows")
    if not isinstance(rows, list) or not rows:
        return JSONResponse({"error": "没有可导入的数据"}, status_code=400)
    ok, failed = 0, []
    for r in rows:
        if not isinstance(r, dict):
            failed.append("非法行")
            continue
        date = str(r.get("date") or "").strip()
        item = str(r.get("item") or "其他").strip()[:40] or "其他"
        category = str(r.get("category") or "其他").strip() or "其他"
        try:
            amount = float(r.get("amount", 0) or 0)
        except (TypeError, ValueError):
            failed.append(item)
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or amount == 0:
            failed.append(item)
            continue
        try:
            await db.add_transaction(date, item, category, amount)
            ok += 1
        except Exception as e:  # noqa: BLE001
            # 检测事务 closed 错误（前一行失败导致 connection state 异常）→ 连接级回滚
            if "cannot operate on a closed database" in str(e).lower() or "no active transaction" in str(e).lower():
                # 单个失败不应影响后续行；记录并继续
                failed.append(f"{item}(事务中断)")
                continue
            failed.append(item)
    return {"ok": True, "imported": ok, "failed": failed}


# ---------------------------------------------------------------------------
# 预算
# ---------------------------------------------------------------------------




@app.get("/api/evaluate")
async def get_evaluate(month: str | None = None) -> dict:
    """运行确定性规则引擎，返回行动项列表（按优先级排序）。
    
    可选 ?month=YYYY-MM，默认本月。结果为纯本地计算，不调用 LLM。
    """
    m = (month or "").strip()
    if m and not re.fullmatch(r"(20\d{2}|19\d{2})-(0[1-9]|1[0-2])", m):
        return JSONResponse({"error": "月份需为 YYYY-MM（01–12）"}, status_code=400)
    return await evaluate.evaluate_all(month=m)


async def _resolve_usable_snapshot(entity: str, entity_id: str):
    """查最近一条 active（未被撤回）快照；没有 raises LookupError。主流程按实体类型传入对应主键值。"""
    rows = await db.list_undo_records(entity=entity, entity_id=str(entity_id), limit=1)
    if not rows:
        raise LookupError(f"no active undo snapshot for {entity}/{entity_id}")
    return rows[0]


VALID_BATCH_UNDO_ENTITIES = ("transactions", "positions", "debts", "subscriptions")
ENTITY_TO_KIND = {
    "transactions": ("transaction",),
    "positions": ("position",),
    "debts": ("debt",),
    "subscriptions": ("subscription",),
}


@app.post("/api/transactions/{tx_id}/undo")
async def undo_transaction(tx_id: int) -> dict:
    try:
        snap = await _resolve_usable_snapshot("transaction", str(tx_id))
    except LookupError:
        return JSONResponse({"error": f"流水 {tx_id} 无可撤回快照"}, status_code=404)
    res = await db._undo_apply(snap["id"])
    return {"ok": True, **res}


@app.post("/api/positions/{symbol}/undo")
async def undo_position(symbol: str) -> dict:
    try:
        snap = await _resolve_usable_snapshot("position", symbol)
    except LookupError:
        return JSONResponse({"error": f"持仓 {symbol} 无可撤回快照"}, status_code=404)
    res = await db._undo_apply(snap["id"])
    return {"ok": True, **res}


@app.post("/api/{entity:path}/batch-undo")
async def batch_undo(entity: str, payload: dict) -> dict:
    entity = (entity or "").strip().lower()
    if entity not in VALID_BATCH_UNDO_ENTITIES:
        return JSONResponse(
            {"error": f"不支持撤回的实体：{entity}，可选：{VALID_BATCH_UNDO_ENTITIES}"},
            status_code=400,
        )
    kind = ENTITY_TO_KIND[entity][0]
    ids = (payload or {}).get("ids")
    if not isinstance(ids, list) or not ids:
        return JSONResponse({"error": "body.ids 需为非空列表"}, status_code=402)

    # 第一步：先全部校验快照可用性（避免部分成功部分失败）
    snapshots: list[tuple[str, int]] = []  # (sid, undo_record_id)
    not_found: list[str] = []
    for raw_id in ids:
        sid = str(raw_id)
        try:
            snap = await _resolve_usable_snapshot(kind, sid)
            snapshots.append((sid, snap["id"]))
        except LookupError:
            not_found.append(sid)

    # 任一快照不可用 → 全不撤回（保持原子语义）
    if not_found:
        return JSONResponse(
            {"error": "部分快照不存在或已被撤回", "not_found": not_found},
            status_code=404,
        )

    # 第二步：逐个执行（所有快照已确认可用）
    results: list[dict] = []
    for sid, undo_id in snapshots:
        res = await db._undo_apply(undo_id)
        results.append({"id": sid, "ok": True, "consumed_at": res["consumed_at"]})
    return {
        "ok": True,
        "succeeded": results,
        "not_found": [],
        "attempted": len(ids),
    }


# ---------------------------------------------------------------------------
# 长期记忆（user_memory）
# ---------------------------------------------------------------------------


@app.get("/api/memory")
async def memory_list() -> dict:
    return {"memory": await db.list_memory()}


@app.post("/api/memory")
async def create_memory(payload: dict) -> dict:
    try:
        out = await db.add_memory(str((payload or {}).get("content") or "").strip())
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)
    return out


@app.delete("/api/memory/{mem_id}")
async def remove_memory(mem_id: int) -> dict:
    return await db.delete_memory(mem_id)


@app.post("/api/memory/clear")
async def clear_memory() -> dict:
    return await db.clear_memory()


@app.post("/api/memory/forget")
async def forget_memory(payload: dict) -> dict:
    """主动遗忘：清理超过 N_used 天未使用的记忆。默认 180 天。"""
    try:
        days = max(1, min(3650, int((payload or {}).get("older_than_days") or 180)))
    except (TypeError, ValueError):
        days = 180
    deleted = await db.forget_memory(days)
    stale = await db.stale_memory_count(days)
    return {"ok": True, "deleted": deleted["deleted"], "still_stale": stale}


# ---------------------------------------------------------------------------
# 经验库（reflections：P1 反思/踩坑复盘）
# ---------------------------------------------------------------------------


@app.get("/api/reflections")
async def reflections(limit: int = 50) -> dict:
    return {"reflections": await db.list_reflections(limit)}


@app.post("/api/reflections")
async def create_reflection(payload: dict) -> dict:
    try:
        out = await db.add_reflection(
            str((payload or {}).get("tool") or "").strip(),
            (payload or {}).get("args") or {},
            str((payload or {}).get("error") or "").strip(),
            str((payload or {}).get("lesson") or "").strip(),
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)
    return out


@app.post("/api/reflections/{ref_id}/resolve")
async def resolve_reflection(ref_id: int) -> dict:
    return await db.resolve_reflection(ref_id)


@app.post("/api/reflections/clear")
async def clear_reflections() -> dict:
    return await db.clear_reflections()


# ---------------------------------------------------------------------------
# 审计日志（P2 金融级治理）
# ---------------------------------------------------------------------------


@app.get("/api/audit")
async def audit_logs(limit: int = 200, action: str | None = None) -> dict:
    return {"audit": await db.list_audit_logs(limit, action)}


@app.post("/api/audit/clear")
async def clear_audit_logs() -> dict:
    return await db.clear_audit_logs()


# ---------------------------------------------------------------------------
# 附件（P2 能力扩展）：上传 / 列出 / 删除
# ---------------------------------------------------------------------------


@app.get("/api/attachments")
async def attachments(limit: int = 50) -> dict:
    return {"attachments": await db.list_attachments(limit)}


@app.post("/api/attachments")
async def upload_attachment(request: Request) -> dict:
    """上传附件（multipart/form-data，字段 file）。文本/CSV 直接提取，PDF 走 pypdf（有则用）。"""
    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001 — 表单解析失败给可读错误
        return JSONResponse({"error": f"表单解析失败：{exc}"}, status_code=400)
    upload = form.get("file")
    if upload is None or not hasattr(upload, "filename"):
        return JSONResponse({"error": "缺少 file 字段"}, status_code=400)
    filename = str(upload.filename or "未命名")
    raw = await upload.read()
    size = len(raw)
    if size > 2 * 1024 * 1024:
        return JSONResponse({"error": "附件过大（最多 2MB）"}, status_code=400)
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        text = ""
    lower = filename.lower()
    kind = "csv" if lower.endswith(".csv") else "text"
    if not text.strip():
        return JSONResponse(
            {"error": "无法读取该文件内容（仅支持文本/CSV）"}, status_code=400
        )
    out = await db.add_attachment(filename, kind, size, text)
    return out


@app.delete("/api/attachments/{att_id}")
async def remove_attachment(att_id: int) -> dict:
    return await db.delete_attachment(att_id)


# ---------------------------------------------------------------------------
# 财务体检（health check）
# ---------------------------------------------------------------------------


@app.get("/api/health-check")
async def health_check(lang: str = "zh") -> dict:
    lang = lang.strip() or "zh"
    positions = await db.list_positions()
    # 空库保护与图内一致：没有任何持仓/流水时不给「分数体检」假象
    if not positions and not await db.fetch_all("SELECT 1 FROM transactions LIMIT 1"):
        return analysis.health_check(None, None, [], await db.list_goals(), lang=lang)
    live = await quotes.live_quotes(positions)
    settings = await db.get_settings()
    m = analysis.market_view(positions, live)
    led = analysis.ledger_view(
        await db.list_transactions(),
        await db.list_subscriptions(),
        await db.list_debts(),
        settings,
        positions,
        live,
    )
    flags = analysis.risk_checks(m, led)
    return analysis.health_check(m, led, flags, await db.list_goals(), lang=lang)


@app.post("/api/portfolio/reset")
async def reset_portfolio() -> dict:
    out = await db.reset_to_seed()
    await invalidate_quotes_cache()
    return out


# ---------------------------------------------------------------------------
# 订阅 / 撤回面板（前端专用薄端点；主数据通过 /api/settings 也能拿到）
# ---------------------------------------------------------------------------




@app.get("/api/undoables")
async def undoables(limit: int = 8) -> dict:
    """最近 N 条可撤回快照（CommandPalette 撤销面板用）。
    返回格式对齐 {entity, entity_id, snapshot_label, created_at}，便于前端直接渲染。"""
    rows = await db.list_undo_records(limit=max(1, min(int(limit), 20)), include_consumed=False)
    items: list[dict[str, Any]] = []
    for r in rows:
        label = _undo_snapshot_label(r)
        items.append(
            {
                "id": r["id"],
                "entity": r["entity"],
                "entity_id": r["entity_id"],
                "label": label,
                "created_at": r["created_at"],
            }
        )
    return {"items": items}


@app.post("/api/undo/{record_id}")
async def undo_by_id(record_id: int) -> dict:
    """通用撤销端点：按 undo_records.id 直接撤回（前端撤销列表首选，无需关心实体类型）。"""
    try:
        res = await db._undo_apply(int(record_id))
    except LookupError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, **res}


def _undo_snapshot_label(r: dict[str, Any]) -> str:
    """把 undo_records 一行翻译为人类可读的一行描述（用于 CommandPalette 展示）。"""
    entity = r["entity"]
    eid = r["entity_id"]
    reason = (r.get("reason") or "").strip()
    before = (r.get("before_json") or "").strip()
    verb = "删除" if before in ("", "{}") else "修改"
    name_map = {
        "transaction": "流水",
        "position": "持仓",
        "debt": "负债",
        "subscription": "订阅",
        "goal": "目标",
    }
    base = f"{name_map.get(entity, entity)} {verb}（{eid}）"
    return f"{base} · {reason}" if reason else base

NUMERIC_KEYS = (
    "monthly_income",
    "emergency_target_months",
    "savings_goal",
    "auto_refresh_seconds",
    "agent_tool_turns",
)
QUOTE_MODES = ("auto", "snapshot", "eastmoney")
COLOR_SCHEMES = ("cn", "us")
DEFAULT_TABS = ("overview", "holdings", "market", "ledger", "chat", "features")
ONOFF_KEYS = (
    "voice_input",
    "show_export",
    "expand_process",
    "show_suggestions",
    "auto_refresh",
    "compact_numbers",
    "ai_enabled",
    "agent_plan",
    "agent_reflect",
)
# AI 配置：文本直存（key 仅存本机数据库）。
# 灵活化：base_url 允许留空走 OpenAI 默认；model 允许留空走模型默认；api_key 可含前缀（sk- 等）。
AI_TEXT_KEYS = ("ai_base_url", "ai_api_key", "ai_model")
# 付费/自由文本设置：直存（长度截断），如晨报关注要点（可 AI 生成）
FREE_TEXT_KEYS = ("report_focus",)
# 模型点亮：逗号分隔的模型名白名单（P0 模型点亮），列表直存但做目录校验
MODEL_LIST_KEYS = ("enabled_models",)
AI_KEY_MAX_LEN = 2000
NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "monthly_income": (0, 1e12),
    "emergency_target_months": (0, 120),
    "savings_goal": (0, 100),
    "auto_refresh_seconds": (30, 86400),
    "agent_tool_turns": (1, 30),
}


@app.get("/api/settings")
async def get_settings() -> dict:
    settings = await db.get_settings()
    _mask_secret(settings)
    return {"settings": settings, "scheduler": scheduler.status()}


@app.put("/api/settings")
async def put_settings(payload: dict) -> dict:
    updates = (payload or {}).get("settings")
    if not isinstance(updates, dict) or not updates:
        return JSONResponse({"error": "settings 对象必填"}, status_code=400)

    applied: dict[str, str] = {}
    errors: list[str] = []
    for key, raw in updates.items():
        if key in NUMERIC_KEYS:
            try:
                v = float(raw)
                lo, hi = NUMERIC_RANGES[key]
                if v < lo or v > hi:
                    errors.append(f"{key} 需在 {lo:g}–{hi:g} 之间")
                    continue
                applied[key] = str(int(v)) if float(v).is_integer() else str(v)
            except (TypeError, ValueError):
                errors.append(f"{key} 的值不合法：{raw!r}")
        elif key in ONOFF_KEYS:
            if raw not in ("on", "off"):
                errors.append(f"{key} 只能是 on/off")
                continue
            applied[key] = raw
        elif key == "quote_source_mode":
            if raw not in QUOTE_MODES:
                errors.append(f"行情源只能是 {'/'.join(QUOTE_MODES)}")
                continue
            applied[key] = raw
        elif key == "color_scheme":
            if raw not in COLOR_SCHEMES:
                errors.append(f"涨跌颜色只能是 {'/'.join(COLOR_SCHEMES)}")
                continue
            applied[key] = raw
        elif key == "default_tab":
            if raw not in DEFAULT_TABS:
                errors.append(f"默认首页只能是 {'/'.join(DEFAULT_TABS)}")
                continue
            applied[key] = raw
        elif key == "report_time":
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(raw).strip()):
                errors.append("晨报时间需为 HH:MM（24 小时制）")
                continue
            applied[key] = str(raw).strip()
        elif key == "essential_categories":
            cats = [c.strip() for c in str(raw).split(",") if c.strip()]
            if not cats:
                errors.append("必要支出类别不能为空")
                continue
            applied[key] = ",".join(cats)
        elif key in FREE_TEXT_KEYS:
            # 自由文本设置：去空白 + 长度截断（200 字），允许清空
            applied[key] = str(raw).strip()[:200]
        elif key in AI_TEXT_KEYS:
            v = str(raw).strip()
            # base_url：可留空（走 OpenAI 默认端点）；填了则必须 http(s)://
            if key == "ai_base_url" and v and not v.startswith(("http://", "https://")):
                errors.append(
                    "AI 接口地址需以 http:// 或 https:// 开头，或留空走默认端点"
                )
                continue
            # api_key：允许任意长度（不同供应商 key 长度差异大，最长 2000 字防误存）
            if key == "ai_api_key" and len(v) > AI_KEY_MAX_LEN:
                errors.append("API Key 过长（最多 2000 字）")
                continue
            # model：可留空（走模型默认）；不限制具体模型名
            # api_key：值为占位符（"********"，即前端未改动）或空串时跳过，保留已存原值
            if key == "ai_api_key":
                if v and v != "********":
                    # vault 加密后再落库；vault 未激活 → 拒绝加密存储
                    if vault.is_active():
                        try:
                            applied[key] = await vault.encrypt_secret(v[:AI_KEY_MAX_LEN])
                        except Exception as e:
                            errors.append(f"API Key 加密失败：{e}")
                    else:
                        errors.append(
                            "VAULT_NOT_INITIALIZED：请先设置 VAULT_PASSPHRASE 环境变量再保存 API Key"
                        )
                # 空串/占位符 → 不写入 applied，保留原 key
            else:
                applied[key] = v
        elif key in MODEL_LIST_KEYS:
            # 模型点亮清单：只收目录内合法模型，非法项忽略（不报错、不写入）
            catalog = {m["model"] for m in llm.model_catalog()}
            if isinstance(raw, str) and raw.strip():
                items = [x.strip() for x in raw.split(",") if x.strip()]
                valid = [x for x in items if x in catalog]
                # 校验不过且一个都没写：报错让用户知道是模型名不合法
                if valid:
                    applied[key] = ",".join(valid)
                else:
                    errors.append(f"模型点亮清单里没有可用的模型：{raw!r}")
            elif isinstance(raw, list):
                valid = [x for x in raw if str(x).strip() in catalog]
                if valid:
                    applied[key] = ",".join(str(x).strip() for x in valid)
                else:
                    errors.append("模型点亮清单为空")
            else:
                applied[key] = ""
        else:
            errors.append(f"未知配置项：{key}")

    for k, v in applied.items():
        await db.set_setting(k, v)
    # AI 配置变化后使 llm 重新读取
    if any(
        k in applied for k in ("ai_enabled", "ai_base_url", "ai_api_key", "ai_model")
    ):
        llm.invalidate()
    if "quote_source_mode" in applied:
        await invalidate_quotes_cache()
    if "report_time" in applied:
        await scheduler.notify_settings_changed()
    return {
        "ok": True,
        "applied": applied,
        "errors": errors,
        "settings": _mask_secret(await db.get_settings()),
    }


# ---------------------------------------------------------------------------
# 问答：SSE 流式
# ---------------------------------------------------------------------------


class _LoopSafeEventSourceResponse(EventSourceResponse):
    """EventSourceResponse 子类：lazy 创建 anyio.Lock 与实例级 exit Event。

    sse-starlette 1.8 有两个跨 event loop 的隐患：
    - __init__ 里创建 `self._send_lock = anyio.Lock()`，绑定到构造时的循环；
    - `listen_for_exit_signal` 把 `anyio.Event()` 缓存在模块级
      `AppStatus.should_exit_event`，第二次及以后的请求在别的循环里 await 它
      会抛 `bound to a different event loop`。

    本服务每次请求都新建 response 并同步 `__call__`（FastAPI 端点内 return 后
    同一 loop 内处理），单 loop 场景行为不变。此子类将 lock 与 exit Event
    都改为实例级、延迟绑定到 `__call__` 所在的 loop，保证任何跨 loop 复用
    （如 pytest-asyncio 每测试一循环）场景下安全，同时保留优雅退出语义。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 覆盖父类在 __init__ 里创建的 lock，占位 None；__call__ 时再绑定
        self._send_lock = None  # type: ignore[assignment]
        self._exit_event = None

    def _ensure_lock(self):
        if self._send_lock is None:
            import anyio

            self._send_lock = anyio.Lock()
        return self._send_lock

    async def listen_for_exit_signal(self):
        """实例级 exit Event（而非模块级缓存），避免跨 loop 绑定报错。"""
        from sse_starlette.sse import AppStatus

        if AppStatus.should_exit:
            return
        if self._exit_event is None:
            import anyio

            self._exit_event = anyio.Event()
        if AppStatus.should_exit:
            return
        await self._exit_event.wait()

    async def __call__(self, scope, receive, send):
        self._ensure_lock()
        return await super().__call__(scope, receive, send)


async def _sse_stream(first: dict | None, runner) -> _LoopSafeEventSourceResponse:
    """把 runner(emit) 产生的事件转成 SSE；断连时取消任务，不继续 yield。

    基于 sse-starlette EventSourceResponse：自带 ping 保活（防代理超时断连）、
    标准 retry 语义、client disconnect 检测。
    前端 fetch-event-source 约定为 `data: {json}` 行：yield 纯 JSON 字符串，
    EventSourceResponse 负责补 `data: ` 前缀与帧分隔，ping 以 `:` 注释行下发
    （浏览器与 fetch-event-source 均忽略），帧格式与手写实现保持一致。
    """

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        def data(obj: dict) -> str:
            return json.dumps(obj, ensure_ascii=False)

        async def emit(event: dict) -> None:
            await queue.put({"type": "event", **event})

        async def run() -> None:
            try:
                await runner(emit)
            except Exception as exc:  # noqa: BLE001 — 回吐脱敏文案，内部细节只进日志
                log.exception("SSE runner error: %s", exc)
                await queue.put(
                    {"type": "error", "message": "生成回答时出错，请稍后再试"}
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        if first is not None:
            yield data(first)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=300)
                except asyncio.TimeoutError:
                    log.warning("SSE runner hung for 300s, force-cancelling")
                    yield data({"type": "error", "message": "响应超时，请重试"})
                    break
                if item is None:
                    break
                yield data(item)
            yield data({"type": "done"})
        finally:
            # client disconnect 或正常结束：确保后台 task 不泄漏
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return _LoopSafeEventSourceResponse(
        event_stream(),
        media_type="text/event-stream",
        ping=15,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/ask")
async def ask(payload: dict):
    question = ((payload or {}).get("question") or "").strip()
    if not question:
        return JSONResponse({"error": "question required"}, status_code=400)
    if len(question) > 2000:
        return JSONResponse({"error": "问题过长（最多 2000 字）"}, status_code=400)
    thread_id = ((payload or {}).get("thread_id") or "").strip() or uuid.uuid4().hex
    regenerate = bool((payload or {}).get("regenerate"))
    lang = ((payload or {}).get("lang") or "zh").strip() or "zh"
    # @提及附件：前端把附件 id 传过来，正文前附加其内容供模型理解
    att_ids = (payload or {}).get("attachments") or []
    attached_text = ""
    if att_ids:
        parts: list[str] = []
        for aid in att_ids:
            try:
                att = await db.get_attachment(int(aid))
            except Exception:  # noqa: BLE001
                att = None
            if att and att.get("content"):
                parts.append(
                    f"【附件：{att.get('filename')}】\n{att['content'][:2000]}"
                )
        if parts:
            attached_text = "\n\n".join(parts)

    async def runner(emit) -> None:
        # 重新生成：先移除该会话最后一条问答，再以同一问题重新作答（替换而非追加）
        if regenerate:
            try:
                await db.delete_last_run(thread_id, question)
            except Exception:  # noqa: BLE001 — 删除失败则退化为普通追加
                log.exception("delete_last_run failed")
        # @提及附件：把附件内容附加到问题正文，供 agent/模板理解
        full_question = (
            question + ("\n\n" + attached_text if attached_text else "")
        ).strip()
        result = await service.run_question(
            full_question, emit, thread_id=thread_id, lang=lang
        )
        # 备份口令：只在当次 SSE 展示，落库前脱敏，确保口令不写入历史/日志
        persisted_answer = result["answer"]
        passphrase = result.get("passphrase")
        if passphrase:
            persisted_answer = persisted_answer.replace(
                str(passphrase), "[口令仅当次展示，不落盘]"
            )
        try:
            await db.save_run(
                thread_id=thread_id,
                question=question,
                answer=persisted_answer,
                level=result["level"],
                flags=result["flags"],
                route=result.get("route", ""),
                llm=result.get("llm", ""),
                route_reason=result.get("route_reason", ""),
                tools=result.get("tools") or [],
                actions=result.get("actions") or [],
            )
        except Exception:  # noqa: BLE001 — 落库失败不打断交付
            log.exception("save_run failed")
        # 长会话压缩（后台异步）：轮次超阈值时把较早轮次折叠成摘要落库，
        # 不阻塞 SSE 交付；失败静默（ensure_session_summary 内部已兜底）。
        # 通过 _spawn_background 持有强引用，防止任务被 GC 静默取消。
        try:
            _spawn_background(service.ensure_session_summary(thread_id))
        except Exception:  # noqa: BLE001 — 摘要任务登记失败不影响主流程
            log.warning("ensure_session_summary schedule failed")
        await emit(
            {
                "type": "final",
                "answer": result["answer"],
                "level": result["level"],
                "route": result["route"],
                "route_reason": result["route_reason"],
                "metrics": result["metrics"],
                "flags": result["flags"],
                "llm": result["llm"],
                "tools": result.get("tools") or [],
                "actions": result.get("actions") or [],
                # 待确认写操作：前端拿 token 显示确认卡片，确认后走 /api/confirm 执行
                "pending_token": result.get("pending_token", ""),
                "pending_summary": result.get("pending_summary", ""),
            }
        )

    # start 事件由 service.run_question 发出（事件契约归 service），此处不再重复发首帧
    return await _sse_stream(None, runner)


# ---------------------------------------------------------------------------
# 待确认写操作（HITL）：token 一次性消费，过期/已消费/已取消 → 409
# ---------------------------------------------------------------------------


@app.post("/api/confirm")
async def confirm(payload: dict):
    token = str((payload or {}).get("token") or "").strip()
    decision = str((payload or {}).get("decision") or "").strip()
    if not token:
        log.warning("confirm: empty token")
        return JSONResponse({"error": "token required"}, status_code=400)
    if decision not in ("confirm", "cancel"):
        log.warning("confirm: bad decision %r", decision)
        return JSONResponse(
            {"error": "decision must be confirm or cancel"}, status_code=400
        )

    log.info("confirm request token=%s decision=%s", token[:12], decision)
    # 进程内 per-token 锁：串行化同一 token 的并发 confirm，防 TOCTOU 重复执行金融写操作
    if len(_confirm_locks) >= _CONCURRENT_HITS_MAX:
        _confirm_locks.popitem(last=False)
    if token not in _confirm_locks:
        _confirm_locks[token] = asyncio.Lock()
    lock = _confirm_locks[token]
    async with lock:
        pending = await db.get_pending_action(token)
        if pending is None:
            log.warning(
                "confirm: token=%s not found (expired/consumed/cancelled/unknown)",
                token[:12],
            )
            return JSONResponse(
                {"error": "动作已失效（过期/已执行/已取消），请重新发起"},
                status_code=409,
            )

        if decision == "cancel":
            await db.mark_pending_action(token, "cancelled")
            log.info(
                "confirm CANCEL token=%s tool=%s summary=%r",
                token[:12],
                pending["tool_name"],
                pending["summary"],
            )
            return {"ok": True, "cancelled": True, "summary": pending["summary"]}

        # 优先走 LangGraph 原生 HITL：从 interrupt 挂起点用 Command(resume) 恢复图，
        # 由 action 节点执行/取消并落库，返回图续跑的最终答案。无挂起线程（进程重启 /
        # 非 interrupt 路径）则降级为直接执行工具（向后兼容）。
        from . import agent_graph

        resumed = await agent_graph.resume_action(token, "confirm")
        if resumed is not None:
            log.info(
                "confirm RESUME token=%s → graph resumed: %s",
                token[:12],
                resumed["level"],
            )
            return {
                "ok": True,
                "tool": pending["tool_name"],
                "answer": resumed["answer"],
                "summary": pending["summary"],
                "graph": True,
            }

        await db.mark_pending_action(token, "consumed")
        from . import tools as tools_mod

        impl = tools_mod.TOOL_IMPL.get(pending["tool_name"])
        if impl is None:
            log.error(
                "confirm: unknown tool %r for token=%s",
                pending["tool_name"],
                token[:12],
            )
            return JSONResponse(
                {"error": f"未知工具：{pending['tool_name']}"}, status_code=400
            )
        try:
            answer = await impl(pending["args"])
            log.info(
                "confirm EXEC token=%s tool=%s args=%s → ok",
                token[:12],
                pending["tool_name"],
                json.dumps(pending["args"], ensure_ascii=False),
            )
        except Exception as exc:  # noqa: BLE001 — 工具失败给可读回执
            log.exception(
                "confirm EXEC failed token=%s tool=%s", token[:12], pending["tool_name"]
            )
            answer = f"执行失败：{type(exc).__name__}: {exc}"
        return {
            "ok": True,
            "tool": pending["tool_name"],
            "answer": answer,
            "summary": pending["summary"],
        }


# ---------------------------------------------------------------------------
# 历史 / 晨报
# ---------------------------------------------------------------------------


@app.get("/api/history")
async def history(thread_id: str | None = None, limit: int = 50, q: str = "") -> dict:
    limit = max(1, min(limit, 500))
    # 全局历史：跨会话搜索（供「全部历史」跳转定位）；指定线程则返回该会话历史
    if q.strip():
        return {"runs": await db.search_runs(q.strip(), limit)}
    return {"runs": await db.list_runs(thread_id, limit)}


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: int) -> dict:
    return await db.delete_run(run_id)


@app.post("/api/history/clear")
async def clear_history() -> dict:
    return await db.clear_history()


# ---------------------------------------------------------------------------
# 会话管理（多会话）
# ---------------------------------------------------------------------------


@app.get("/api/sessions")
async def sessions() -> dict:
    return {"sessions": await db.list_sessions()}


@app.post("/api/sessions")
async def create_session(payload: dict | None = None) -> dict:
    title = str((payload or {}).get("title") or "新会话").strip()
    return await db.create_session(title=title)


@app.patch("/api/sessions/{session_id}")
async def rename_session(session_id: int, payload: dict) -> dict:
    title = str(payload.get("title") or "").strip()
    if not title:
        return JSONResponse({"error": "标题不能为空"}, status_code=400)
    return await db.rename_session(session_id, title)


@app.post("/api/sessions/{session_id}/migrate")
async def migrate_session_runs(session_id: int, request: Request) -> dict:
    """把乐观新建窗口内挂在临时线程下的 runs 迁入真实会话。"""
    from_tid = request.query_params.get("from", "").strip()
    if not from_tid:
        return JSONResponse({"error": "from required"}, status_code=400)
    real_tid = await db.session_thread_id(session_id)
    if not real_tid:
        return JSONResponse({"error": "session not found"}, status_code=404)
    moved = await db.move_runs(from_tid, real_tid)
    return {"ok": True, "moved": moved}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: int) -> dict:
    return await db.delete_session(session_id)


# ---------------------------------------------------------------------------
# 数据导出 / 导入恢复 / 月度趋势
# ---------------------------------------------------------------------------


@app.get("/api/export")
async def export_data(passphrase: str | None = None) -> dict:
    """全量导出：无口令 → 明文 JSON（兼容旧版）；有口令 → 加密备份包（推荐）。"""
    data = await db.export_data()
    _mask_secret(data.get("settings", {}))
    if passphrase:
        return backup.encrypt_export(data, passphrase)
    return data


@app.post("/api/import/backup")
async def import_backup(payload: dict) -> dict:
    """从 /api/export 的 JSON 恢复全量数据（AI Key 除外，需重新填写）。

    加密备份包（encrypted=true）必须携带 passphrase 字段，口令错误会拒绝并回滚。
    """
    payload = payload or {}
    if not isinstance(payload, dict):
        return JSONResponse({"error": "备份格式不正确"}, status_code=400)
    if payload.get("encrypted"):
        passphrase = str(payload.get("passphrase") or "")
        if not passphrase:
            return JSONResponse({"error": "加密备份需要口令"}, status_code=400)
        try:
            data = backup.decrypt_export(payload, passphrase)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    else:
        data = payload
    version = str((data.get("meta") or {}).get("version") or data.get("version") or "")
    if not (version.startswith(("wealth-office-v", "xiaoman-v")) or version == "2"):
        return JSONResponse(
            {"error": f"备份格式不被识别（version={version or '空'}）"}, status_code=400
        )
    try:
        counts = await db.import_backup(data)
    except Exception as exc:  # noqa: BLE001 — 恢复失败要回滚并给可读错误
        log.exception("import backup failed")
        return JSONResponse({"error": f"恢复失败，数据已回滚：{exc}"}, status_code=400)
    await invalidate_quotes_cache()
    return {"ok": True, "counts": counts}


@app.get("/api/export/csv")
async def export_csv() -> StreamingResponse:
    """流水导出为 CSV（带 BOM，Excel 直接打开不乱码）。"""
    import csv
    import io

    rows = await db.list_transactions()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["日期", "项目", "分类", "金额"])

    # 防 CSV 公式注入：以 = + - @ 开头的单元格加单引号前缀，避免 Excel 打开执行公式
    def _safe(v: str) -> str:
        v = str(v or "")
        return "'" + v if v and v[0] in "=+-@" else v

    for r in rows:
        writer.writerow(
            [
                _safe(r["date"]),
                _safe(r["item"]),
                _safe(r["category"]),
                _safe(r["amount"]),
            ]
        )
    data = "\ufeff" + buf.getvalue()
    return StreamingResponse(
        iter([data]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ledger.csv"'},
    )




@app.get("/api/reports")
async def reports(limit: int = 20) -> dict:
    return {"reports": await db.list_runs("cron", limit)}


@app.post("/api/reports/generate")
async def generate_report_now() -> dict:
    try:
        result = await scheduler.generate_report()
    except Exception as exc:  # noqa: BLE001 — 手动触发失败要给可读错误
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    if result.get("skipped"):
        # 空库不生成（前端据此提示「还没有数据」而非假装成功）
        return {"ok": True, "skipped": True, "reason": result.get("reason", "no_data")}
    return {"ok": True, "answer": result["answer"], "level": result["level"]}


@app.get("/api/scheduler")
async def scheduler_status() -> dict:
    return scheduler.status()


# ---------------------------------------------------------------------------
# MCP Server：小满财务工具 → MCP 协议（Claude Code / Cursor / 任何 MCP Client 接入）
# ---------------------------------------------------------------------------

_mcp_enabled = os.getenv("MCP_ENABLE", "1") == "1"
if _mcp_enabled:
    from .mcp_server import mount_to_app

    mount_to_app(app)


# ---------------------------------------------------------------------------
# 日志查看接口
# ---------------------------------------------------------------------------


@app.get("/api/logs")
async def get_logs(limit: int = 200) -> dict:
    """返回日志文件最近 limit 行（从尾部），供前端日志页使用。"""
    lines = read_log_lines(min(max(1, limit), 1000))
    return {"lines": lines, "total": len(lines)}


@app.post("/api/logs/clear")
async def clear_logs_endpoint() -> dict:
    """清空日志文件，返回清空前行数。"""
    cleared = clear_logs()
    log.info("logs cleared manually (%d lines removed)", cleared)
    return {"ok": True, "cleared_lines": cleared}


# ---------------------------------------------------------------------------
# Agent 配置：角色 / skills / 工具开关
# ---------------------------------------------------------------------------

@app.get("/api/agent-config")
async def get_agent_config() -> dict:
    """读当前 agent 配置（角色/skills/工具）。"""
    from . import agent_config
    cfg = await agent_config.get_config()
    return {"ok": True, "config": cfg}


@app.post("/api/agent-config")
async def update_agent_config(payload: dict) -> dict:
    """更新 agent 配置。"""
    from . import agent_config
    new_cfg = payload.get("config", payload)
    await agent_config.update_config(new_cfg)
    return {"ok": True}


@app.post("/api/agent-config/generate")
async def generate_agent_config(payload: dict) -> dict:
    """AI 一键生成：按自然语言描述生成 skill / 角色描述（设置页「AI 生成」按钮）。

    只产出建议不落库，由用户在设置页确认后随既有保存流程写入。
    未接入模型或模型输出不可用 → 200 + {"ok": false, "error": ...}（fail-closed）。
    """
    from . import agent_config, llm

    kind = str((payload or {}).get("kind") or "skill").strip()
    prompt = str((payload or {}).get("prompt") or "").strip()
    agent_name = str((payload or {}).get("agent") or "").strip()
    if not prompt:
        return {"ok": False, "error": "请先描述你想要的效果"}
    if not await llm.llm_available():
        return {"ok": False, "error": "未接入模型 —— 先到「设置 → AI 回答」配置模型端点"}
    suggestion = await agent_config.generate_suggestion(kind, prompt, agent_name)
    if suggestion is None:
        return {"ok": False, "error": "生成失败，请换个描述再试"}
    return {"ok": True, "suggestion": suggestion}


# ---------------------------------------------------------------------------
# 静态前端托管（同域单端口）
# ---------------------------------------------------------------------------

if FRONTEND_DIST.is_dir():

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(
            FRONTEND_DIST / "index.html",
            headers={"Cache-Control": "no-store"},
        )

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="web")
else:

    @app.get("/", include_in_schema=False)
    async def placeholder() -> dict:
        return {"message": "前端未构建：cd frontend && npm install && npm run build"}
