"""组合库 + 运行历史持久化（aiosqlite，单连接串行，不阻塞事件循环）。

所有函数都是异步的；连接在启动时创建（WAL 模式）。
首次运行自动建表。全新库为**空账本**（不种示例数据）：用户从记第一笔/添加持仓开始；
示例数据仅在设置页显式"导入示例数据"时种入（演示用）。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

_default_db = Path(__file__).resolve().parent.parent / "data" / "wealth.db"
DB_PATH = Path(os.getenv("XIAOMAN_DB_PATH", str(_default_db)))

_db: aiosqlite.Connection | None = None
_inited = False

# --------------------------------------------------------------------------
# 家庭共享：当前活跃成员 session store（进程内，单实例部署够用）
# _ACTIVE_KEY 是进程级"当前 session" key；多 session 部署应换 JWT / cookie / Redis
# --------------------------------------------------------------------------
_ACTIVE_KEY = "__default__"
_active_member_id: dict[str, int | None] = {}  # session_key → member_id

# 预定义配色池，轮流给新成员分配
_AVATAR_COLORS = [
    "#b8891f", "#2e7d32", "#1565c0", "#6a1b9a", "#c62828",
    "#00838f", "#ef6c00", "#37474f", "#ad1457", "#3949ab",
]


def set_active_member(member_id: int | None, session_key: str = _ACTIVE_KEY) -> None:
    """切换当前活跃成员"""
    _active_member_id[session_key] = member_id


def get_active_member(session_key: str = _ACTIVE_KEY) -> int | None:
    """获取当前活跃成员 id"""
    return _active_member_id.get(session_key)


async def _fetch_member(member_id: int) -> dict[str, Any] | None:
    """根据 id 取成员信息"""
    conn = await _conn()
    cur = await conn.execute(
        "SELECT id, username, display_name, role, avatar_color, created_at "
        "FROM members WHERE id=?", (member_id,)
    )
    row = await cur.fetchone()
    return dict(row) if row else None

# --------------------------------------------------------------------------
# 种子数据：一套典型中产家庭的示例（用户可在"记账"页改成自己的真实数据）
# --------------------------------------------------------------------------

SEED_POSITIONS = [
    {
        "symbol": "600519",
        "name": "贵州茅台",
        "kind": "股票",
        "industry": "白酒",
        "shares": 100,
        "cost": 1680.00,
        "last": 1521.00,
    },
    {
        "symbol": "510300",
        "name": "沪深300ETF",
        "kind": "ETF",
        "industry": "宽基指数",
        "shares": 8000,
        "cost": 3.85,
        "last": 4.06,
    },
    {
        "symbol": "110011",
        "name": "易方达中小盘混合",
        "kind": "基金",
        "industry": "主动权益",
        "shares": 12000,
        "cost": 4.10,
        "last": 3.58,
    },
    {
        "symbol": "CASH",
        "name": "活期现金",
        "kind": "现金",
        "industry": "现金",
        "shares": 1,
        "cost": 55000.00,
        "last": 55000.00,
    },
]

# day_in_month: 尽量落在本月已过去的日期（今日之前），保证"本月"口径成立
SEED_TRANSACTIONS = [
    (2, "工资入账", "收入", 24800.0),
    (3, "房租", "居住", -5200.0),
    (5, "外卖餐饮", "餐饮", -1860.0),
    (7, "视频会员（年付）", "订阅", -258.0),
    (9, "通勤地铁", "交通", -320.0),
    (11, "健身私教", "订阅", -1999.0),
    (13, "添置家电", "购物", -4300.0),
    (15, "基金定投", "投资", -3000.0),
    (17, "云盘会员", "订阅", -168.0),
    (19, "聚餐", "餐饮", -960.0),
    (20, "信用卡还款", "还款", -3200.0),
]

SEED_SUBSCRIPTIONS = [
    {"name": "云盘会员", "monthly": 14.0, "note": "可合并到家庭共享", "due_day": "1"},
    {
        "name": "健身私教",
        "monthly": 1999.0,
        "note": "占订阅支出绝大部分",
        "due_day": "5",
    },
    {"name": "流媒体", "monthly": 21.5, "note": "与年付会员功能重叠", "due_day": "28"},
]

SEED_DEBTS = [
    {
        "name": "房贷",
        "monthly": 6800.0,
        "balance": 1280000.0,
        "rate": 0.0345,
        "due_day": "15",
    },
    {
        "name": "信用卡分期",
        "monthly": 900.0,
        "balance": 7200.0,
        "rate": 0.13,
        "due_day": "10",
    },
]

SEED_SETTINGS = {
    "monthly_income": "24800",
    "emergency_target_months": "6",
    # 应急金覆盖所需的"必要月支出"口径：居住 + 餐饮 + 交通 三类
    "essential_categories": "居住,餐饮,交通",
    # 行情源：auto（东财优先，失败降级快照）| snapshot | eastmoney
    "quote_source_mode": "auto",
    # 定时晨报时间（HH:MM）
    "report_time": "08:00",
    # ---- 功能开关（设置中心可自定义）----
    "voice_input": "off",  # 问答语音输入（浏览器支持时）
    "show_export": "on",  # 回答导出/复制按钮
    "expand_process": "off",  # 分析过程默认展开
    "show_suggestions": "off",  # 问答页建议入口（R4 起输入区常驻快捷指令 chips，空态建议默认关）
    "auto_refresh": "off",  # 仪表盘定时自动刷新
    "auto_refresh_seconds": "300",  # 自动刷新间隔（秒）
    "compact_numbers": "on",  # 大金额缩写（万/亿）
    "color_scheme": "cn",  # 涨跌颜色：cn 红涨绿跌（A股惯例）| us 绿涨红跌（海外惯例）
    "default_tab": "chat",  # 默认首页：overview|holdings|market|ledger|chat（对话中枢为主，可在设置改回）
    "savings_goal": "20",  # 储蓄率目标（%）
    # ---- AI 回答（OpenAI 兼容端点，可配任意国产/海外模型；失败自动降级模板）----
    "ai_enabled": "on",  # 是否启用 AI 回答（AI 优先；三要素未配或调用失败时回退内置分析）
    "ai_base_url": "",  # 国产示例：DeepSeek https://api.deepseek.com/v1 · 豆包 https://ark.cn-beijing.volces.com/api/v3 · 通义 https://dashscope.aliyuncs.com/compatible-mode/v1
    "ai_api_key": "",  # 仅存本机数据库
    "ai_model": "",  # 对应端点模型：deepseek-chat / doubao 接入点 ID / qwen-plus
    # ---- 模型点亮：设置页可勾选启用哪些模型，逗号分隔的模型名（默认点亮前两个）----
    "enabled_models": "deepseek-chat,qwen-plus",
    # ---- Agent 行为（可配置化：工具轮次 / 规划展示 / 失败反思重试）----
    "agent_tool_turns": "5",  # 单轮问答里模型可调用工具的轮次上限（1-30，防死循环）
    "agent_plan": "on",  # 是否展示执行计划（supervisor 计划卡 / 推理轨迹）
    "agent_reflect": "on",  # 工具失败时是否提示模型反思修正后重试
    "data_note": "seed",
}

# 版本化默认设置：新增键时对已有库补齐默认值
DEFAULT_SETTINGS = {k: v for k, v in SEED_SETTINGS.items()}

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    symbol   TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    kind     TEXT NOT NULL DEFAULT '股票',
    industry TEXT NOT NULL DEFAULT '其他',
    shares   REAL NOT NULL,
    cost     REAL NOT NULL,
    last     REAL NOT NULL,
    buy_date TEXT,
    fee      REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    date     TEXT NOT NULL,
    item     TEXT NOT NULL,
    category TEXT NOT NULL,
    amount   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_month ON transactions(date);
CREATE TABLE IF NOT EXISTS subscriptions (
    name    TEXT PRIMARY KEY,
    monthly REAL NOT NULL,
    note    TEXT NOT NULL DEFAULT '',
    due_day TEXT NOT NULL DEFAULT ''   -- 每月几号扣款（'' 表示未设置）
);
CREATE TABLE IF NOT EXISTS debts (
    name     TEXT PRIMARY KEY,
    monthly  REAL NOT NULL,
    balance  REAL NOT NULL,
    rate     REAL NOT NULL,
    due_day  TEXT NOT NULL DEFAULT ''  -- 每月几号还款（'' 表示未设置）
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS budgets (
    month    TEXT NOT NULL,   -- YYYY-MM
    category TEXT NOT NULL,   -- __total 表示总预算，其余为分类预算
    amount   REAL NOT NULL,
    PRIMARY KEY (month, category)
);
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id     TEXT NOT NULL,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    level         TEXT NOT NULL DEFAULT '',
    flags_json    TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL,
    route         TEXT NOT NULL DEFAULT '',
    llm           TEXT NOT NULL DEFAULT '',
    route_reason  TEXT NOT NULL DEFAULT '',
    tools         TEXT NOT NULL DEFAULT '',
    actions       TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_runs_thread ON runs(thread_id, id);
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id  TEXT UNIQUE NOT NULL,
    title      TEXT NOT NULL DEFAULT '新会话',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
    name       TEXT PRIMARY KEY,
    target     REAL NOT NULL,
    saved      REAL NOT NULL DEFAULT 0,
    deadline   TEXT NOT NULL DEFAULT '',   -- 目标月份 YYYY-MM（'' 未设）
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol     TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    kind       TEXT NOT NULL DEFAULT '股票',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'fact', -- fact / preference / goal_related
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_actions (
    token      TEXT PRIMARY KEY,
    tool_name  TEXT NOT NULL,
    args       TEXT NOT NULL,
    summary    TEXT NOT NULL,
    lang       TEXT NOT NULL DEFAULT 'zh',
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending / consumed / cancelled / expired
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_summary (
    thread_id  TEXT PRIMARY KEY,
    summary    TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'llm',  -- llm / heuristic / reset
    covered_to INTEGER NOT NULL DEFAULT 0,   -- 已纳入摘要的最新 runs.id
    updated_at TEXT NOT NULL
);
-- 经验库（P1 反思）：记录工具失败的「踩坑点」，下次反思时参考，避免重复犯错。
CREATE TABLE IF NOT EXISTS reflections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tool        TEXT NOT NULL,
    args_json   TEXT NOT NULL DEFAULT '{}',
    error       TEXT NOT NULL DEFAULT '',
    lesson      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    resolved_at TEXT NOT NULL DEFAULT ''     -- 非空表示已被「后来成功」标记解决
);
-- 审计追踪 Provenance：每个金额变动操作的完整来龙去脉
CREATE TABLE IF NOT EXISTS provenance_log (
    id           TEXT PRIMARY KEY,
    timestamp    TEXT NOT NULL,
    action       TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT,
    before_json  TEXT,
    after_json   TEXT,
    source       TEXT NOT NULL DEFAULT 'api',
    username     TEXT NOT NULL DEFAULT 'system',
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_provenance_entity ON provenance_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_provenance_timestamp ON provenance_log(timestamp);
-- 审计日志（P2 金融级治理）：记录写操作与敏感读，支持追溯。
CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    action      TEXT NOT NULL,          -- WRITE / READ_SENSITIVE / AUTH
    method      TEXT NOT NULL,
    path        TEXT NOT NULL,
    status      INTEGER NOT NULL,
    actor       TEXT NOT NULL DEFAULT '', -- 来源 IP / 用户标识
    detail      TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts DESC);
-- 附件（P2 能力扩展）：对话中引用本地文件，附文本内容供模型理解。
CREATE TABLE IF NOT EXISTS attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'text',   -- text / csv / pdf
    size        INTEGER NOT NULL DEFAULT 0,
    content     TEXT NOT NULL DEFAULT '',       -- 提取后的文本内容（上限）
    created_at  TEXT NOT NULL
);
-- 撤销记录（P2 金融级治理）：流水 / 持仓 / 负债 / 订阅 / 目标写操作前的全量快照，
-- 供 undo 端点恢复原状。before_json 为空串 '{}' 表示实体此前不存在（新增前的快照）。
CREATE TABLE IF NOT EXISTS undo_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    entity         TEXT NOT NULL,     -- transaction | position | debt | subscription | goal
    entity_id      TEXT NOT NULL,     -- 实体主键值（position.symbol / transactions.id / debt.name 等）
    before_json    TEXT NOT NULL,     -- 旧行 JSON；空串 '{}' 表示实体此前不存在（INSERT 前的快照）
    reason         TEXT NOT NULL DEFAULT '',
    consumed_at    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_undo_entity ON undo_records(entity, entity_id);
CREATE INDEX IF NOT EXISTS idx_undo_consumed ON undo_records(consumed_at);
-- 用户体系（P0 多租户）：bcrypt 哈希 + 下次登录修改密码标志 + 软删除
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT 'user',  -- admin | user
    disabled     INTEGER NOT NULL DEFAULT 0,
    last_login   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
-- 加密密钥封装（P0 安全加固）：Fernet 密钥由口令派生后加密存储在 DB，
-- 解密时调用方提供主口令 → 临时解密出 Fernet 密钥 → 用于加解密 ai_api_key 等敏感配置。
-- 这避免了在 DB 里明文落 ai_api_key / 邮件 smtp 密码等。
CREATE TABLE IF NOT EXISTS vault_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key_name    TEXT UNIQUE NOT NULL,           -- 'app'（全局应用密钥）等
    enc_key     TEXT NOT NULL,                  -- 加密后的 Fernet key (b64)
    kdf_salt    TEXT NOT NULL,                  -- b64 salt
    kdf_iters   INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
-- 家庭成员表：家庭共享账本的核心实体
CREATE TABLE IF NOT EXISTS members (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT 'member',  -- owner/admin/member/viewer
    avatar_color TEXT NOT NULL DEFAULT '#b8891f',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
-- 成员间借贷
CREATE TABLE IF NOT EXISTS member_loans (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    from_member_id INTEGER NOT NULL REFERENCES members(id),
    to_member_id   INTEGER NOT NULL REFERENCES members(id),
    amount         REAL NOT NULL,
    currency       TEXT NOT NULL DEFAULT 'CNY',
    note           TEXT NOT NULL DEFAULT '',
    settled        INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    settled_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_member_loans_from ON member_loans(from_member_id);
CREATE INDEX IF NOT EXISTS idx_member_loans_to ON member_loans(to_member_id);
"""


def _seed_date(day: int) -> str:
    """种子流水的日期：本月已过去的日期（不晚于今天）。"""
    now = datetime.now()
    return now.replace(day=min(day, now.day)).strftime("%Y-%m-%d")


async def init_db() -> None:
    global _db, _inited
    if _inited:
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(DB_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")   # SQLite 默认关外键；显式打开以启用 FK 约束/级联
    await _db.executescript(SCHEMA)
    await _migrate_add_columns()
    # 全新库（settings 表为空）不再自动种示例：空账本起步，用户自己记账/加持仓。
    # 老库即使用户清空了数据也绝不重置；示例数据只能显式导入（设置页/演示 API）。
    await _ensure_defaults()
    if await _count("positions") == 0:
        conn = await _conn()
        row = await (
            await conn.execute("SELECT value FROM settings WHERE key='data_note'")
        ).fetchone()
        if row and str(row["value"]).startswith("seed"):
            # 若旧库被清空但 data_note 仍是 seed，降级为 empty，避免误标示例
            await conn.execute(
                "INSERT INTO settings(key,value) VALUES('data_note','empty') "
                "ON CONFLICT(key) DO UPDATE SET value='empty'"
            )
            await conn.commit()
    await _migrate_sessions_from_runs()
    await _db.commit()
    _inited = True


async def _migrate_add_columns() -> None:
    """老库增量迁移：为已有表补新列（CREATE TABLE IF NOT EXISTS 不会改老表）。"""
    assert _db is not None
    cols = {
        "subscriptions": {"due_day": "TEXT NOT NULL DEFAULT ''"},
        "debts": {"due_day": "TEXT NOT NULL DEFAULT ''"},
        # 问答来源可溯源：route/llm 落库后历史回答也能显示真实来源（此前只能显示等级）
        "runs": {
            "route": "TEXT NOT NULL DEFAULT ''",
            "llm": "TEXT NOT NULL DEFAULT ''",
            "route_reason": "TEXT NOT NULL DEFAULT ''",
            "tools": "TEXT NOT NULL DEFAULT ''",
            "actions": "TEXT NOT NULL DEFAULT '[]'",
        },
        # 主动遗忘：记录每次被注入/使用的时间，便于按未使用时长清理
        "user_memory": {"last_used": "TEXT NOT NULL DEFAULT ''"},
    }
    # transactions 表：新增 owner_id（交易归属成员）与 is_shared（是否共享）
    tx_cols = await _db.execute("PRAGMA table_info(transactions)")
    tx_existing = {row["name"] for row in await tx_cols.fetchall()}
    if "owner_id" not in tx_existing:
        await _db.execute(
            "ALTER TABLE transactions ADD COLUMN owner_id INTEGER REFERENCES members(id)"
        )
    if "is_shared" not in tx_existing:
        await _db.execute(
            "ALTER TABLE transactions ADD COLUMN is_shared INTEGER NOT NULL DEFAULT 1"
        )

    for table, adds in cols.items():
        cur = await _db.execute(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in await cur.fetchall()}
        for col, decl in adds.items():
            if col not in existing:
                await _db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


# --------------------------------------------------------------------------
# 用户体系（多租户基础）
# --------------------------------------------------------------------------

async def user_create(username: str, password: str, display_name: str = "",
                      role: str = "user") -> int:
    """创建用户，返回行 id。username 唯一；密码 bcrypt 哈希。"""
    from passlib.hash import bcrypt
    pw_hash = bcrypt.using(rounds=12).hash(password)
    conn = await _conn()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    cur = await conn.execute(
        "INSERT INTO users(username, password_hash, display_name, role, created_at) "
        "VALUES(?,?,?,?,?)",
        (username, pw_hash, display_name or username, role, now),
    )
    await conn.commit()
    return cur.lastrowid


async def user_get_by_username(username: str) -> dict[str, Any] | None:
    conn = await _conn()
    cur = await conn.execute(
        "SELECT id, username, password_hash, display_name, role, disabled, last_login, created_at "
        "FROM users WHERE username=?", (username,)
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def user_get(uid: int) -> dict[str, Any] | None:
    conn = await _conn()
    cur = await conn.execute(
        "SELECT id, username, password_hash, display_name, role, disabled, last_login, created_at "
        "FROM users WHERE id=?", (uid,)
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def user_verify_password(user: dict[str, Any], password: str) -> bool:
    from passlib.hash import bcrypt
    try:
        return bcrypt.verify(password, user["password_hash"])
    except Exception:
        return False


async def user_update_last_login(uid: int) -> None:
    conn = await _conn()
    await conn.execute(
        "UPDATE users SET last_login=? WHERE id=?",
        (datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), uid),
    )
    await conn.commit()


async def user_count() -> int:
    conn = await _conn()
    cur = await conn.execute("SELECT COUNT(*) AS n FROM users WHERE disabled=0")
    row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def close_db() -> None:
    global _db, _inited
    if _db is not None:
        await _db.close()
    _db = None
    _inited = False


async def _conn() -> aiosqlite.Connection:
    if _db is None:
        await init_db()
    assert _db is not None
    return _db


def _clean_due_day(v: object) -> str:
    """扣款日归一化：'' / '1'..'31'；非法值返回 ''。"""
    s = str(v or "").strip()
    if s in {"", "0"}:
        return ""
    if s.isdigit() and 1 <= int(s) <= 31:
        return s
    return ""


_COUNT_ALLOWED_TABLES = frozenset({"transactions", "positions", "budgets", "goals", "subscriptions", "members", "runs", "audit_log", "transactions_fts"})
_LIST_LIMIT_MAX = 500


def _clamp_limit(limit: int, default: int = 50) -> int:
    """限制分页上限，防止 limit=9999999 导致内存爆炸。"""
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return default
    if n <= 0:
        return default
    return min(n, _LIST_LIMIT_MAX)


async def _count(table: str) -> int:
    if table not in _COUNT_ALLOWED_TABLES:
        raise ValueError(f"disallowed table for _count: {table!r}")
    cur = await _db.execute(f"SELECT COUNT(*) AS n FROM {table}")
    row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def _seed_all() -> None:
    assert _db is not None
    await _db.executemany(
        "INSERT INTO positions(symbol,name,kind,industry,shares,cost,last,buy_date,fee)"
        " VALUES(:symbol,:name,:kind,:industry,:shares,:cost,:last,:buy_date,:fee)",
        [{**p, "buy_date": None, "fee": 0.0} for p in SEED_POSITIONS],
    )
    await _db.executemany(
        "INSERT INTO transactions(date,item,category,amount) VALUES(?,?,?,?)",
        [(_seed_date(d), item, cat, amt) for d, item, cat, amt in SEED_TRANSACTIONS],
    )
    await _db.executemany(
        "INSERT INTO subscriptions(name,monthly,note,due_day) VALUES(:name,:monthly,:note,:due_day)",
        [{**s, "due_day": s.get("due_day", "")} for s in SEED_SUBSCRIPTIONS],
    )
    await _db.executemany(
        "INSERT INTO debts(name,monthly,balance,rate,due_day) VALUES(:name,:monthly,:balance,:rate,:due_day)",
        [{**d, "due_day": d.get("due_day", "")} for d in SEED_DEBTS],
    )
    await _db.executemany(
        "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
        list(SEED_SETTINGS.items()),
    )


async def _ensure_defaults() -> None:
    """对已有库补齐新增的设置默认键（版本化迁移）。"""
    conn = await _conn()
    await conn.executemany(
        "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
        list(DEFAULT_SETTINGS.items()),
    )
    # 空库标记 data_note=empty：与示例库（seed）区分，前端据此不显示示例数据横幅
    if await _count("positions") == 0:
        await conn.execute(
            "INSERT INTO settings(key,value) VALUES('data_note','empty') "
            "ON CONFLICT(key) DO UPDATE SET value='empty'"
        )


async def _migrate_sessions_from_runs() -> None:
    """历史迁移：已有问答（旧库）按 thread 生成会话，标题取该线程首个问题。

    系统归档线程（cron 晨报、skill:<id> 技能定时触发）不属于「问AI」会话列表：
    它们由 save_run(skip_session=True) 写入，此处也必须一并排除，否则重启时会把
    系统产出补建成会话、污染会话列表（skip_session 只拦写入侧）。
    同时自愈清理历史版本已误建的系统线程会话行。
    """
    conn = await _conn()
    await conn.execute(
        "DELETE FROM sessions WHERE thread_id='cron' OR thread_id LIKE 'skill:%'"
    )
    rows = await (
        await conn.execute(
            "SELECT r.thread_id, r.question FROM runs r"
            " WHERE r.id = (SELECT MIN(id) FROM runs WHERE thread_id = r.thread_id)"
            "   AND r.thread_id <> 'cron' AND r.thread_id NOT LIKE 'skill:%'"
            "   AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.thread_id = r.thread_id)"
        )
    ).fetchall()
    if not rows:
        await conn.commit()
        return
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for r in rows:
        await conn.execute(
            "INSERT OR IGNORE INTO sessions(thread_id,title,created_at,updated_at)"
            " VALUES(?,?,?,?)",
            (r["thread_id"], str(r["question"])[:40] or "新会话", now, now),
        )


async def reset_to_seed() -> dict[str, Any]:
    """清空并重新种入示例数据（演示/测试用）。

    只重置示例数据本身（持仓/流水/订阅/负债/预算）与 data_note 标记；用户设置
    （AI 端点与密钥、Agent 配置、偏好、账本假设）一律保留——「恢复示例数据」
    不应把用户的模型密钥与个性化配置一起清掉（e2e 复用在跑的研发服务时同理）。
    """
    conn = await _conn()
    for t in (
        "positions",
        "transactions",
        "subscriptions",
        "debts",
        "budgets",
    ):
        await conn.execute(f"DELETE FROM {t}")
    # 数据已换回种子 → data_note 标回 seed；其余 settings 全部保留
    await conn.execute(
        "INSERT INTO settings(key,value) VALUES('data_note','seed') "
        "ON CONFLICT(key) DO UPDATE SET value='seed'"
    )
    await _seed_all()
    await conn.commit()
    return {"ok": True, "reset": True}


# --------------------------------------------------------------------------
# 读
# --------------------------------------------------------------------------


async def fetch_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn = await _conn()
    cur = await conn.execute(sql, params)
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def fetch_one(sql: str, params: tuple = ()) -> aiosqlite.Row | None:
    """执行查询并返回单行结果（无匹配返回 None）。"""
    conn = await _conn()
    cur = await conn.execute(sql, params)
    return await cur.fetchone()


async def execute(sql: str, params: tuple = ()) -> None:
    """执行写语句（INSERT/UPDATE/DELETE）并提交。"""
    conn = await _conn()
    await conn.execute(sql, params)
    await conn.commit()


async def list_positions() -> list[dict[str, Any]]:
    return await fetch_all("SELECT * FROM positions ORDER BY symbol")


async def list_transactions(member_id: int | None = None) -> list[dict[str, Any]]:
    """列出交易流水。

    - member_id=None：返回所有流水 + 无 owner 的流水（向后兼容单用户模式）
    - member_id=0 or specific id：返回 shared=1 的流水 + 自己拥有的流水
    """
    if member_id is None:
        return await fetch_all("SELECT * FROM transactions ORDER BY date DESC, id DESC")
    # 有 member_id：共享流水 + 自己的流水（含私有）
    return await fetch_all(
        "SELECT * FROM transactions WHERE is_shared=1 OR owner_id=? "
        "ORDER BY date DESC, id DESC",
        (member_id,),
    )


async def list_subscriptions() -> list[dict[str, Any]]:
    return await fetch_all("SELECT * FROM subscriptions ORDER BY name")


async def list_debts() -> list[dict[str, Any]]:
    return await fetch_all("SELECT * FROM debts ORDER BY name")


async def get_settings() -> dict[str, str]:
    rows = await fetch_all("SELECT * FROM settings")
    return {r["key"]: r["value"] for r in rows}


# --------------------------------------------------------------------------
# 预算（budgets：month + category → amount；__total 为总预算）
# --------------------------------------------------------------------------


async def list_budgets(month: str) -> list[dict[str, Any]]:
    return await fetch_all(
        "SELECT month, category, amount FROM budgets WHERE month=? ORDER BY category",
        (month,),
    )


# 预算口径排除项：投资/还款属于储蓄或资金转移，不是消费支出，不计入预算使用
NON_CONSUMPTION_CATEGORIES: tuple[str, ...] = ("投资", "还款")


async def budget_usage(month: str) -> dict[str, Any]:
    """当月预算使用情况：与 /api/budgets 返回的 usage 字段同源。

    返回：
    - total_budget / total_spent / total_pct / over / left / left_daily / days_left
    - categories: [{category, budget, spent, pct, over}]
    """

    rows = await list_budgets(month)
    spent_by_cat = await month_expense_by_category(month)
    for cat in NON_CONSUMPTION_CATEGORIES:
        spent_by_cat.pop(cat, None)
    total_spent = round(sum(spent_by_cat.values()), 2)
    total_budget = next((r["amount"] for r in rows if r["category"] == "__total"), 0.0)

    cat_usage = []
    for r in rows:
        key = r["category"]
        if key == "__total":
            continue
        budget = float(r["amount"] or 0)
        spent = round(spent_by_cat.get(key, 0.0), 2)
        cat_usage.append({
            "category": "总预算" if key == "__total" else key,
            "budget": budget,
            "spent": spent,
            "pct": round(spent / budget * 100, 1) if budget else 0,
            "over": spent > budget,
        })

    total_pct = round(total_spent / total_budget * 100, 1) if total_budget else 0
    now = datetime.now().astimezone()
    next_month = datetime(
        now.year + (now.month == 12), (now.month % 12) + 1, 1, tzinfo=now.tzinfo
    )
    days_left = max(1, (next_month - now.replace(hour=0, minute=0, second=0, microsecond=0)).days)
    left_daily = round((total_budget - total_spent) / days_left, 2) if total_budget else 0.0

    return {
        "total_budget": total_budget,
        "total_spent": total_spent,
        "total_pct": total_pct,
        "over": total_budget > 0 and total_spent > total_budget,
        "left": round(total_budget - total_spent, 2),
        "left_daily": left_daily,
        "days_left": days_left,
        "categories": cat_usage,
    }


async def total_cash() -> float:
    """活期现金总额：position 中 kind='现金' 的行 shares*last 求和（无现金行返回 0）。

    注意：这只是活期头寸，不含投资/股票/基金市值。
    """
    rows = await fetch_all(
        "SELECT SUM(shares * last) AS cash FROM positions WHERE kind = '现金'"
    )
    return float((rows[0].get("cash") or 0) if rows else 0.0)


async def save_budgets(month: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """整月替换式保存：先删该月旧预算，再写入新列表。

    同月重复分类取最后一项（主键 (month,category) 不允许重复）；
    任一语句失败整体回滚，避免 DELETE 已执行而 INSERT 未完成的半截状态。
    """
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError(f"budget month 格式非法: {month!r}，应为 YYYY-MM")
    conn = await _conn()
    seen: dict[str, float] = {}
    for it in items:
        cat = str(it.get("category", "")).strip() or "__total"
        amt = float(it.get("amount", 0) or 0)
        if amt <= 0:
            continue
        seen[cat[:40]] = amt
    try:
        await conn.execute("DELETE FROM budgets WHERE month=?", (month,))
        for cat, amt in seen.items():
            await conn.execute(
                "INSERT INTO budgets(month,category,amount) VALUES(?,?,?)",
                (month, cat, amt),
            )
        await conn.commit()
    except Exception:  # aqg: top-level boundary — 事务失败统一回滚后原样抛出，不吞异常
        await conn.rollback()
        raise
    return {"ok": True, "month": month, "count": len(seen)}


async def month_expense_by_category(month: str) -> dict[str, float]:
    """当月支出按分类汇总（amount<0 视为支出，取绝对值）。"""
    rows = await fetch_all(
        "SELECT category, SUM(-amount) AS spent FROM transactions"
        " WHERE date LIKE ? AND amount < 0 GROUP BY category",
        (f"{month}%",),
    )
    return {r["category"]: float(r["spent"] or 0) for r in rows}


# --------------------------------------------------------------------------
# 写
# --------------------------------------------------------------------------


async def add_position(p: dict[str, Any]) -> dict[str, Any]:
    conn = await _conn()
    clean = {
        "symbol": str(p.get("symbol", "")).strip(),
        "name": str(p.get("name", "")).strip() or "未命名",
        "kind": str(p.get("kind", "股票")).strip() or "股票",
        "industry": str(p.get("industry", "其他")).strip() or "其他",
        "shares": float(p.get("shares", 0) or 0),
        "cost": float(p.get("cost", 0) or 0),
        "last": float(p.get("last", 0) or 0),
        "buy_date": (str(p.get("buy_date") or "").strip() or None),
        "fee": float(p.get("fee", 0) or 0),
    }
    if not clean["symbol"]:
        raise ValueError("代码不能为空")
    if clean["shares"] <= 0 or clean["shares"] != clean["shares"]:
        raise ValueError("股数需大于 0")
    if clean["cost"] < 0 or clean["cost"] != clean["cost"]:
        raise ValueError("成本价不能为负")
    if clean["last"] < 0 or clean["last"] != clean["last"]:
        raise ValueError("现价不能为负")
    if clean["fee"] < 0 or clean["fee"] != clean["fee"]:
        raise ValueError("费用不能为负")
    # 撤销快照：记录 upsert 前的状态（已存在 → 旧行 JSON，新增 → '{}'）
    existing = await (
        await conn.execute("SELECT * FROM positions WHERE symbol=?", (clean["symbol"],))
    ).fetchone()
    await _record_snapshot("position", clean["symbol"], _row_to_json(existing))
    await conn.execute(
        "INSERT INTO positions(symbol,name,kind,industry,shares,cost,last,buy_date,fee)"
        " VALUES(:symbol,:name,:kind,:industry,:shares,:cost,:last,:buy_date,:fee)"
        " ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, kind=excluded.kind,"
        " industry=excluded.industry, shares=excluded.shares, cost=excluded.cost,"
        " last=excluded.last, buy_date=excluded.buy_date, fee=excluded.fee",
        clean,
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "symbol": clean["symbol"]}


async def delete_position(symbol: str) -> dict[str, Any]:
    conn = await _conn()
    # 撤销快照：记录删除前的全量旧行，撤回时 INSERT OR REPLACE 恢复
    old = await (
        await conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,))
    ).fetchone()
    if old is None:
        return {"ok": False, "deleted": 0}
    await _record_snapshot("position", symbol, _row_to_json(old))
    cur = await conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


async def update_position(p: dict[str, Any], symbol: str) -> dict[str, Any]:
    """编辑指定 symbol 的持仓。fields 里缺的键保持原值；校验与 add_position 一致。"""
    conn = await _conn()
    cur = await conn.execute(
        "SELECT name,kind,industry,shares,cost,last,buy_date,fee FROM positions WHERE symbol=?",
        (symbol,),
    )
    row = await cur.fetchone()
    if row is None:
        raise ValueError(f"持仓 {symbol} 不存在")
    old = {
        "name": row[0],
        "kind": row[1],
        "industry": row[2],
        "shares": row[3],
        "cost": row[4],
        "last": row[5],
        "buy_date": row[6],
        "fee": row[7],
    }
    # 撤销快照：写入前的全量旧行，撤回时恢复
    await _record_snapshot(
        "position",
        symbol,
        json.dumps({"symbol": symbol, **old}, ensure_ascii=False, default=str),
    )
    clean = {
        "name": str(p.get("name", old["name"])).strip() or old["name"],
        "kind": str(p.get("kind", old["kind"])).strip() or old["kind"],
        "industry": str(p.get("industry", old["industry"])).strip() or old["industry"],
        "shares": float(p.get("shares", old["shares"])),
        "cost": float(p.get("cost", old["cost"])),
        "last": float(p.get("last", old["last"])),
        "buy_date": (str(p.get("buy_date", old["buy_date"] or "")).strip() or None),
        "fee": float(p.get("fee", old["fee"])),
    }
    if clean["shares"] <= 0 or clean["shares"] != clean["shares"]:
        raise ValueError("股数需大于 0")
    if clean["cost"] < 0 or clean["cost"] != clean["cost"]:
        raise ValueError("成本价不能为负")
    if clean["last"] < 0 or clean["last"] != clean["last"]:
        raise ValueError("现价不能为负")
    if clean["fee"] < 0 or clean["fee"] != clean["fee"]:
        raise ValueError("费用不能为负")
    await conn.execute(
        "UPDATE positions SET name=:name, kind=:kind, industry=:industry,"
        " shares=:shares, cost=:cost, last=:last, buy_date=:buy_date, fee=:fee"
        " WHERE symbol=:symbol",
        {**clean, "symbol": symbol},
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "symbol": symbol}


async def merge_positions_by_name(name: str) -> dict[str, Any]:
    """同名不同 symbol 的持仓合并成一条：保留最早录入那条的 symbol，
    股数求和、成本/现价/费用加权平均。返回合并掉的条数。"""
    nm = str(name).strip()
    if not nm:
        raise ValueError("名称不能为空")
    conn = await _conn()
    # 合并快照需要全量字段，以备撤回时按 symbol 完整恢复每一行
    cur = await conn.execute(
        "SELECT * FROM positions WHERE name=? ORDER BY symbol",
        (nm,),
    )
    old_rows = [dict(r) for r in await cur.fetchall()]
    if len(old_rows) <= 1:
        return {"ok": True, "merged": 0}

    # 撤销快照：为合并涉及的所有行各存一份完整旧行 JSON，撤回时按 symbol 各自 INSERT OR REPLACE
    for r in old_rows:
        await _record_snapshot(
            "position", r["symbol"], json.dumps(r, ensure_ascii=False, default=str)
        )

    rows = [
        {
            "symbol": r["symbol"],
            "shares": r["shares"],
            "cost": r["cost"],
            "last": r["last"],
            "fee": r["fee"],
        }
        for r in old_rows
    ]

    # 保留最早录入那条（created_at 最小 / symbol 字典序最小兜底），其余合并进它
    keep = rows[0]
    total_shares = sum(r["shares"] for r in rows if r["shares"] > 0)
    if total_shares <= 0:
        total_shares = keep["shares"]

    # 成本/现价/费用按股数加权平均（share=0 的条目权重取 1）
    def _wavg(field: str) -> float:
        num = 0.0
        den = 0.0
        for r in rows:
            w = r["shares"] if r["shares"] > 0 else 1.0
            num += r[field] * w
            den += w
        return round(num / den, 6) if den else 0.0

    merged_cost = _wavg("cost")
    merged_last = _wavg("last")
    # 佣金（fee）是每笔持仓的总额，合并时求和而非加权平均
    merged_fee = round(sum(r["fee"] for r in rows), 6)

    await conn.execute(
        "UPDATE positions SET shares=?, cost=?, last=?, fee=? WHERE symbol=?",
        (total_shares, merged_cost, merged_last, merged_fee, keep["symbol"]),
    )
    for r in rows[1:]:
        await conn.execute("DELETE FROM positions WHERE symbol=?", (r["symbol"],))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "merged": len(rows) - 1, "symbol": keep["symbol"]}


# --------------------------------------------------------------------------
# 自选行情（watchlist）
# --------------------------------------------------------------------------


async def list_watchlist() -> list[dict[str, Any]]:
    conn = await _conn()
    cur = await conn.execute(
        "SELECT symbol,name,kind,created_at FROM watchlist ORDER BY created_at"
    )
    rows = await cur.fetchall()
    return [
        {"symbol": r[0], "name": r[1], "kind": r[2], "created_at": r[3]} for r in rows
    ]


async def add_watchlist(
    symbol: str, name: str = "", kind: str = "股票"
) -> dict[str, Any]:
    sym = str(symbol).strip().upper()
    if not sym:
        raise ValueError("代码不能为空")
    import datetime as _dt

    conn = await _conn()
    await conn.execute(
        "INSERT INTO watchlist(symbol,name,kind,created_at) VALUES(?,?,?,?)"
        " ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, kind=excluded.kind",
        (
            sym,
            str(name).strip()[:40] or sym,
            str(kind).strip()[:10] or "股票",
            _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        ),
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "symbol": sym}


async def delete_watchlist(symbol: str) -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute(
        "DELETE FROM watchlist WHERE symbol=?", (symbol.strip().upper(),)
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


async def add_transaction(
    date: str, item: str, category: str, amount: float,
    owner_id: int | None = None, is_shared: bool | None = None,
) -> dict[str, Any]:
    """入账唯一入口：所有路径（手动 / 一句话记账 / CSV 导入）都必须经过这里。

    在此统一做真实日历校验与金额校验——`2026-13-99` 这类正则放行的
    脏日期会污染月度统计（趋势 / 预算 / 现金流），必须在写入前拦截。

    owner_id: 归属成员 id；未指定时尝试取当前活跃成员，无活跃成员则为 NULL（我的账本模式）
    is_shared: 是否共享；未指定时 owner 身份自动 1，viewer/member 默认 0（私有）
    """
    d = str(date).strip()
    amt = float(amount)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        raise ValueError(f"日期需为 YYYY-MM-DD：{d!r}") from None
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"日期不是有效日历日：{d!r}") from None
    if amt == 0 or amt != amt:  # NaN / 0 都拒绝
        raise ValueError("金额不能为 0 或 NaN")

    # 解析 owner_id
    resolved_owner = owner_id
    if resolved_owner is None:
        active = _active_member_id.get(_ACTIVE_KEY)
        if active is not None:
            resolved_owner = active

    # 解析 is_shared
    resolved_shared = is_shared
    if resolved_shared is None and resolved_owner is not None:
        # 查成员角色：owner/admin 的流水自动共享
        m = await _fetch_member(resolved_owner)
        resolved_shared = bool(m and m.get("role") in ("owner", "admin"))
    if resolved_shared is None:
        resolved_shared = 1  # 默认值：无 owner 时保持向后兼容

    conn = await _conn()
    cur = await conn.execute(
        "INSERT INTO transactions(date,item,category,amount,owner_id,is_shared) VALUES(?,?,?,?,?,?)",
        (
            d,
            str(item).strip()[:80] or "未命名",
            str(category).strip()[:20] or "其他",
            amt,
            resolved_owner,
            1 if resolved_shared else 0,
        ),
    )
    # 撤销快照：新增前 before_json='{}'，撤回时按 entity_id(=id) 可以直接 DELETE 这条新流水
    await _record_snapshot("transaction", str(cur.lastrowid), "{}")
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "id": cur.lastrowid}


async def delete_transaction(tx_id: int) -> dict[str, Any]:
    conn = await _conn()
    # 撤销快照：记录删除前的全量旧行，撤回时 INSERT OR REPLACE 恢复
    old = await (
        await conn.execute("SELECT * FROM transactions WHERE id=?", (int(tx_id),))
    ).fetchone()
    if old is None:
        return {"ok": False, "deleted": 0}
    await _record_snapshot("transaction", str(tx_id), _row_to_json(old))
    cur = await conn.execute("DELETE FROM transactions WHERE id=?", (int(tx_id),))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


async def update_transaction(
    tx_id: int,
    *,
    date: str | None = None,
    item: str | None = None,
    category: str | None = None,
    amount: float | None = None,
    owner_id: int | str | None = None,
    is_shared: bool | None = None,
) -> dict[str, Any]:
    """编辑一条流水。只传需要改的字段（None 表示不动），金额 0 / NaN 拒绝。"""

    conn = await _conn()
    cur = await conn.execute(
        "SELECT date,item,category,amount,owner_id,is_shared FROM transactions WHERE id=?",
        (int(tx_id),),
    )
    row = await cur.fetchone()
    if row is None:
        raise ValueError(f"流水 {tx_id} 不存在")
    old_date, old_item, old_cat, old_amt = row["date"], row["item"], row["category"], row["amount"]
    old_owner = row["owner_id"]
    old_shared = row["is_shared"]
    # 撤销快照：写入操作前的全量旧行（4 列），撤回时恢复
    await _record_snapshot(
        "transaction",
        str(tx_id),
        json.dumps(
            {
                "id": int(tx_id),
                "date": old_date,
                "item": old_item,
                "category": old_cat,
                "amount": old_amt,
                "owner_id": old_owner,
                "is_shared": old_shared,
            },
            ensure_ascii=False,
        ),
    )

    d = str(date).strip() if date is not None else old_date
    it = str(item).strip()[:80] if item is not None else old_item
    cat = (str(category).strip()[:20] or "其他") if category is not None else old_cat
    amt = float(amount) if amount is not None else old_amt
    own = int(owner_id) if owner_id is not None and owner_id != "" else old_owner
    shr = (1 if is_shared else 0) if is_shared is not None else old_shared

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        raise ValueError(f"日期需为 YYYY-MM-DD：{d!r}")
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"日期不是有效日历日：{d!r}") from None
    if not it:
        it = "未命名"
    if amt == 0 or amt != amt:
        raise ValueError("金额不能为 0 或 NaN")

    await conn.execute(
        "UPDATE transactions SET date=?,item=?,category=?,amount=?,owner_id=?,is_shared=? WHERE id=?",
        (d, it, cat, amt, own, shr, int(tx_id)),
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "id": int(tx_id)}


async def merge_transactions(
    month: str,
    category: str | None = None,
) -> dict[str, Any]:
    """合并同类流水：把指定月份（可选指定分类）下所有流水，按 (date,item,category) 求和合并成一组，
    保留每组最早一条，删其余。返回合并掉的条数。
    """
    m = str(month).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", m):
        raise ValueError("月份需为 YYYY-MM")
    cat = str(category).strip() if category else None

    conn = await _conn()
    if cat:
        cur = await conn.execute(
            "SELECT date,item,category,amount FROM transactions"
            " WHERE date >= ? AND date < ? AND category=? ORDER BY date,item",
            (f"{month}-01", f"{month}-32", cat),
        )
    else:
        cur = await conn.execute(
            "SELECT date,item,category,amount FROM transactions"
            " WHERE date >= ? AND date < ? ORDER BY date,item,category",
            (f"{month}-01", f"{month}-32"),
        )
    rows = [
        {"date": r[0], "item": r[1], "category": r[2], "amount": r[3]}
        for r in (await cur.fetchall())
    ]

    # 按 (date, item, category) 分组求和
    groups: dict[tuple[str, str, str], float] = {}
    group_order: list[tuple[str, str, str]] = []
    for r in rows:
        key = (r["date"], r["item"], r["category"])
        if key not in groups:
            groups[key] = 0.0
            group_order.append(key)
        groups[key] += r["amount"]

    merged = 0
    for key, total in groups.items():
        d, it, cat_ = key
        # 找该组最早那条，更新金额为合计
        cur2 = await conn.execute(
            "SELECT id FROM transactions WHERE date=? AND item=? AND category=? LIMIT 1",
            (d, it, cat_),
        )
        first_id = (await cur2.fetchone())[0]
        if total == 0 or total != total:
            # 合计为 0 或 NaN → 整组删掉
            await conn.execute(
                "DELETE FROM transactions WHERE date=? AND item=? AND category=?",
                (d, it, cat_),
            )
            merged += 1
            continue
        await conn.execute(
            "UPDATE transactions SET amount=? WHERE id=?",
            (total, first_id),
        )
        # 删该组除最早外的其余记录
        cur3 = await conn.execute(
            "DELETE FROM transactions WHERE date=? AND item=? AND category=? AND id<>?",
            (d, it, cat_, first_id),
        )
        merged += cur3.rowcount

    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "merged": merged}


async def add_debt(d: dict[str, Any]) -> dict[str, Any]:
    conn = await _conn()
    clean = {
        "name": str(d.get("name", "")).strip(),
        "monthly": float(d.get("monthly", 0) or 0),
        "balance": float(d.get("balance", 0) or 0),
        "rate": float(d.get("rate", 0) or 0),
        "due_day": _clean_due_day(d.get("due_day", "")),
    }
    if not clean["name"]:
        raise ValueError("名称不能为空")
    # 撤销快照：upsert 前的状态（已存在=旧行，新增='{}'）
    existing = await (
        await conn.execute("SELECT * FROM debts WHERE name=?", (clean["name"],))
    ).fetchone()
    await _record_snapshot("debt", clean["name"], _row_to_json(existing))
    await conn.execute(
        "INSERT INTO debts(name,monthly,balance,rate,due_day) VALUES(:name,:monthly,:balance,:rate,:due_day)"
        " ON CONFLICT(name) DO UPDATE SET monthly=excluded.monthly,"
        " balance=excluded.balance, rate=excluded.rate, due_day=excluded.due_day",
        clean,
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "name": clean["name"]}


async def delete_debt(name: str) -> dict[str, Any]:
    conn = await _conn()
    # 撤销快照：记录删除前的完整旧行，撤回时 INSERT OR REPLACE 恢复
    old = await (
        await conn.execute("SELECT * FROM debts WHERE name=?", (name,))
    ).fetchone()
    if old is None:
        return {"ok": False, "deleted": 0}
    await _record_snapshot("debt", name, _row_to_json(old))
    cur = await conn.execute("DELETE FROM debts WHERE name=?", (name,))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


async def add_subscription(s: dict[str, Any]) -> dict[str, Any]:
    conn = await _conn()
    clean = {
        "name": str(s.get("name", "")).strip(),
        "monthly": float(s.get("monthly", 0) or 0),
        "note": str(s.get("note", "")).strip(),
        "due_day": _clean_due_day(s.get("due_day", "")),
    }
    if not clean["name"]:
        raise ValueError("名称不能为空")
    if clean["monthly"] <= 0:
        raise ValueError("月支出需大于 0")
    # 撤销快照：upsert 前的状态（已存在=旧行，新增='{}'）
    existing = await (
        await conn.execute("SELECT * FROM subscriptions WHERE name=?", (clean["name"],))
    ).fetchone()
    await _record_snapshot("subscription", clean["name"], _row_to_json(existing))
    await conn.execute(
        "INSERT INTO subscriptions(name,monthly,note,due_day) VALUES(:name,:monthly,:note,:due_day)"
        " ON CONFLICT(name) DO UPDATE SET monthly=excluded.monthly,"
        " note=excluded.note, due_day=excluded.due_day",
        clean,
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "name": clean["name"]}


async def delete_subscription(name: str) -> dict[str, Any]:
    conn = await _conn()
    # 撤销快照：记录删除前的完整旧行，撤回时 INSERT OR REPLACE 恢复
    old = await (
        await conn.execute("SELECT * FROM subscriptions WHERE name=?", (name,))
    ).fetchone()
    if old is None:
        return {"ok": False, "deleted": 0}
    await _record_snapshot("subscription", name, _row_to_json(old))
    cur = await conn.execute("DELETE FROM subscriptions WHERE name=?", (name,))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


# --------------------------------------------------------------------------
# 财务目标（goals）
# --------------------------------------------------------------------------


async def list_goals() -> list[dict[str, Any]]:
    return await fetch_all("SELECT * FROM goals ORDER BY created_at DESC, name")


async def add_goal(g: dict[str, Any]) -> dict[str, Any]:
    """新增目标。字段：name / target / saved（可选）/ deadline（可选，YYYY-MM）。"""
    name = str(g.get("name") or "").strip()[:40]
    if not name:
        raise ValueError("目标名称必填")
    try:
        target = float(g.get("target", 0) or 0)
    except (TypeError, ValueError):
        raise ValueError("目标金额不合法") from None
    if target <= 0:
        raise ValueError("目标金额需大于 0")
    try:
        saved = max(0.0, float(g.get("saved", 0) or 0))
    except (TypeError, ValueError):
        saved = 0.0
    deadline = str(g.get("deadline") or "").strip()[:7]
    conn = await _conn()
    await conn.execute(
        "INSERT INTO goals(name,target,saved,deadline,created_at)"
        " VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET"
        " target=excluded.target, saved=excluded.saved, deadline=excluded.deadline",
        (
            name,
            target,
            saved,
            deadline,
            datetime.now().astimezone().isoformat(timespec="seconds"),
        ),
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {
        "ok": True,
        "name": name,
        "target": target,
        "saved": saved,
        "deadline": deadline,
    }


async def update_goal(name: str, patch: dict[str, Any]) -> dict[str, Any]:
    """更新目标的部分字段（target/saved/deadline）。"""
    name = str(name or "").strip()
    if not name:
        raise ValueError("目标名称必填")
    fields: list[str] = []
    params: list[Any] = []
    for key in ("target", "saved", "deadline"):
        if key not in patch:
            continue
        if key == "deadline":
            v = str(patch[key] or "").strip()[:7]
        else:
            try:
                v = float(patch[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} 不合法") from None
            if key == "target" and v <= 0:
                raise ValueError("目标金额需大于 0")
            if key == "saved":
                v = max(0.0, v)
        fields.append(f"{key}=?")
        params.append(v)
    if not fields:
        raise ValueError("没有可更新的字段")
    conn = await _conn()
    cur = await conn.execute(
        f"UPDATE goals SET {', '.join(fields)} WHERE name=?", [*params, name]
    )
    await _mark_user_data(conn)
    await conn.commit()
    if cur.rowcount == 0:
        raise ValueError("目标不存在")
    return {"ok": True, "name": name}


async def delete_goal(name: str) -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute("DELETE FROM goals WHERE name=?", (name,))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


# --------------------------------------------------------------------------
# 长期记忆（user_memory：agent 记住用户长期信息）
# --------------------------------------------------------------------------


async def list_memory() -> list[dict[str, Any]]:
    return await fetch_all(
        "SELECT * FROM user_memory ORDER BY updated_at DESC, id DESC"
    )


def memory_retrieve(
    query: str, rows: list[dict[str, Any]], top_k: int = 5
) -> list[dict[str, Any]]:
    """BM25 关键词检索（rank-bm25 库打分，无 embedding Key 的确定性语义检索降级）。

    小满记忆为少量长文本（几十~几百条），用 BM25 打分足够：按查询词频/逆文档
    频率给每条记忆打分取 top_k，命中即返回并排序。打分数学交给 rank-bm25
    （其 idf 带负值修正，比手写实现更稳）；中文双字+单字分词是领域定制，
    保留自实现。当后续接入 embedding API 时，可替换为本函数同签名
    （query→embeddings→余弦相似度）的向量实现，无缝升级。
    返回命中的记忆条目；空查询返回空。
    """
    q = str(query or "").strip().lower()
    if not q or not rows:
        return []

    # 中文按双字 + 单字切分（双字利于语义，单字兜底避免"买"与"买房子"错配），英文按词
    def _tokens(text: str) -> list[str]:
        text = str(text).lower()
        toks: list[str] = []
        for seg in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", text):
            if re.fullmatch(r"[\u4e00-\u9fff]+", seg):
                for i in range(len(seg) - 1):
                    toks.append(seg[i : i + 2])
                for ch in seg:
                    toks.append(ch)
            else:
                toks.append(seg)
        return toks

    from rank_bm25 import BM25L

    corpus = [r.get("content") or "" for r in rows]
    # 用 BM25L 而非 BM25Okapi：记忆语料很小（几~几百条），Okapi 的 idf 公式在
    # n≈N 时会得到 0 甚至负值，导致命中全部归零被过滤；BM25L 的 idf 带 +1，
    # 恒为正，与真实语料规模下的检索预期一致。
    bm25 = BM25L([_tokens(c) for c in corpus])
    scores = bm25.get_scores(_tokens(q))
    scored = sorted(zip(scores, rows, strict=True), key=lambda x: x[0], reverse=True)
    return [r for s, r in scored[:top_k] if s > 0]


async def add_memory(content: str, kind: str = "fact") -> dict[str, Any]:
    """写入一条长期记忆；内容完全相同则只刷新时间戳（天然去重）。"""
    content = str(content or "").strip()
    if not content:
        raise ValueError("记忆内容不能为空")
    if len(content) > 500:
        content = content[:500]
    kind = str(kind or "fact").strip()[:20] or "fact"
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    conn = await _conn()
    cur = await conn.execute(
        "SELECT id FROM user_memory WHERE content=? LIMIT 1", (content,)
    )
    row = await cur.fetchone()
    if row:
        await conn.execute(
            "UPDATE user_memory SET updated_at=?, kind=? WHERE id=?",
            (now, kind, row["id"]),
        )
        await conn.commit()
        return {"ok": True, "id": row["id"], "deduped": True}
    await conn.execute(
        "INSERT INTO user_memory(content,kind,created_at,updated_at) VALUES(?,?,?,?)",
        (content, kind, now, now),
    )
    await _mark_user_data(conn)
    await conn.commit()
    cur = await conn.execute("SELECT last_insert_rowid() AS id")
    row = await cur.fetchone()
    return {"ok": True, "id": row["id"]}


async def delete_memory(mem_id: int) -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute("DELETE FROM user_memory WHERE id=?", (mem_id,))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


async def clear_memory() -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute("DELETE FROM user_memory")
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


async def delete_memory_by_kind(kind: str) -> dict[str, Any]:
    """按 kind 精确匹配批量删除 user_memory（用于同月订阅提醒去重 + 其他分类清理）。"""
    if not kind:
        return {"ok": False, "reason": "empty kind"}
    conn = await _conn()
    cur = await conn.execute("DELETE FROM user_memory WHERE kind=?", (kind,))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


async def touch_memory(mem_id: int) -> dict[str, Any]:
    """记忆被注入/使用时刷新 last_used（主动遗忘：只淘汰长期未用）。"""
    conn = await _conn()
    await conn.execute(
        "UPDATE user_memory SET last_used=? WHERE id=?",
        (datetime.now().astimezone().isoformat(timespec="seconds"), int(mem_id)),
    )
    await conn.commit()
    return {"ok": True}


async def forget_memory(older_than_days: int = 180) -> dict[str, Any]:
    """主动遗忘：删除超过 N 天未被使用的记忆。last_used 为空视为最近录入不删。

    返回删除条数；用于设置页「清理久未使用的记忆」。
    """
    conn = await _conn()
    import datetime as _dt

    cutoff = (
        _dt.datetime.now().astimezone() - _dt.timedelta(days=int(older_than_days))
    ).isoformat(timespec="seconds")
    cur = await conn.execute(
        "DELETE FROM user_memory WHERE last_used != '' AND last_used < ?",
        (cutoff,),
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount or 0}


async def stale_memory_count(older_than_days: int = 180) -> int:
    """统计超过 N 天未使用的记忆条数（供前端提示）。"""
    import datetime as _dt

    cutoff = (
        _dt.datetime.now().astimezone() - _dt.timedelta(days=int(older_than_days))
    ).isoformat(timespec="seconds")
    rows = await fetch_all(
        "SELECT COUNT(*) AS n FROM user_memory WHERE last_used != '' AND last_used < ?",
        (cutoff,),
    )
    return int(rows[0]["n"]) if rows else 0


# --------------------------------------------------------------------------
# 经验库（reflections：P1 反思/踩坑复盘）
# --------------------------------------------------------------------------


async def add_reflection(
    tool: str, args: dict[str, Any], error: str, lesson: str
) -> dict[str, Any]:
    """记录一次工具失败的「踩坑点」。同一 (tool, lesson) 近场合并去重。"""
    tool = str(tool or "").strip()[:60]
    error = str(error or "").strip()[:500]
    lesson = str(lesson or "").strip()[:400]
    if not tool:
        raise ValueError("tool 不能为空")
    conn = await _conn()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    # 相同工具 + 相同教训 → 去重（仅刷新时间），避免一条错误刷屏几十条
    dup = await (
        await conn.execute(
            "SELECT id FROM reflections WHERE tool=? AND lesson=? AND resolved_at='' LIMIT 1",
            (tool, lesson),
        )
    ).fetchone()
    if dup:
        await conn.execute(
            "UPDATE reflections SET created_at=?, args_json=? WHERE id=?",
            (now, json.dumps(args or {}, ensure_ascii=False)[:800], dup["id"]),
        )
        await conn.commit()
        return {"ok": True, "id": dup["id"], "deduped": True}
    cur = await conn.execute(
        "INSERT INTO reflections(tool,args_json,error,lesson,created_at)"
        " VALUES(?,?,?,?,?)",
        (tool, json.dumps(args or {}, ensure_ascii=False)[:800], error, lesson, now),
    )
    await conn.commit()
    return {"ok": True, "id": cur.lastrowid, "deduped": False}


async def list_reflections(limit: int = 50) -> list[dict[str, Any]]:
    """列出未解决的踩坑点（新→旧）。"""
    rows = await fetch_all(
        "SELECT id, tool, args_json, error, lesson, created_at, resolved_at"
        " FROM reflections WHERE resolved_at='' ORDER BY created_at DESC, id DESC LIMIT ?",
        (_clamp_limit(limit),),
    )
    for r in rows:
        try:
            r["args"] = json.loads(r.pop("args_json") or "{}")
        except Exception:  # noqa: BLE001
            r["args"] = {}
    return rows


async def resolve_reflection(ref_id: int) -> dict[str, Any]:
    """标记某条踩坑已解决（后来成功），不再提示。"""
    conn = await _conn()
    await conn.execute(
        "UPDATE reflections SET resolved_at=? WHERE id=?",
        (datetime.now().astimezone().isoformat(timespec="seconds"), int(ref_id)),
    )
    await conn.commit()
    return {"ok": True}


async def clear_reflections() -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute("DELETE FROM reflections")
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount or 0}


# --------------------------------------------------------------------------
# 审计日志（P2 金融级治理）
# --------------------------------------------------------------------------


async def add_audit_log(
    action: str,
    method: str,
    path: str,
    status: int,
    actor: str = "",
    detail: str = "",
    duration_ms: int = 0,
) -> dict[str, Any]:
    """写一条审计日志。action: WRITE / READ_SENSITIVE / AUTH。"""
    conn = await _conn()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    await conn.execute(
        "INSERT INTO audit_logs(ts,action,method,path,status,actor,detail,duration_ms)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (
            now,
            str(action)[:20],
            str(method)[:8],
            str(path)[:200],
            int(status or 0),
            str(actor)[:64],
            str(detail)[:500],
            int(duration_ms or 0),
        ),
    )
    await conn.commit()
    return {"ok": True}


async def list_audit_logs(
    limit: int = 200, action: str | None = None
) -> list[dict[str, Any]]:
    """列审计日志（新→旧），可按类型过滤。"""
    clamped = _clamp_limit(limit, default=200)
    if action:
        rows = await fetch_all(
            "SELECT * FROM audit_logs WHERE action=? ORDER BY id DESC LIMIT ?",
            (str(action)[:20], clamped),
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (clamped,)
        )
    return rows


async def clear_audit_logs() -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute("DELETE FROM audit_logs")
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount or 0}


# --------------------------------------------------------------------------
# 附件（P2 能力扩展）
# --------------------------------------------------------------------------


async def list_attachments(limit: int = 50) -> list[dict[str, Any]]:
    rows = await fetch_all(
        "SELECT id, filename, kind, size, created_at FROM attachments ORDER BY id DESC LIMIT ?",
        (_clamp_limit(limit),),
    )
    return rows


async def add_attachment(
    filename: str, kind: str, size: int, content: str
) -> dict[str, Any]:
    conn = await _conn()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    cur = await conn.execute(
        "INSERT INTO attachments(filename,kind,size,content,created_at) VALUES(?,?,?,?,?)",
        (
            str(filename)[:200],
            str(kind)[:20] or "text",
            int(size or 0),
            content[:6000],
            now,
        ),
    )
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "id": cur.lastrowid}


async def get_attachment(att_id: int) -> dict[str, Any] | None:
    rows = await fetch_all("SELECT * FROM attachments WHERE id=?", (int(att_id),))
    return rows[0] if rows else None


async def delete_attachment(att_id: int) -> dict[str, Any]:
    conn = await _conn()
    cur = await conn.execute("DELETE FROM attachments WHERE id=?", (int(att_id),))
    await _mark_user_data(conn)
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount or 0}


async def set_setting(key: str, value: str) -> dict[str, Any]:
    conn = await _conn()
    await conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(key), str(value)),
    )
    await conn.commit()
    return {"ok": True}


async def _mark_user_data(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        "INSERT INTO settings(key,value) VALUES('data_note','user') "
        "ON CONFLICT(key) DO UPDATE SET value='user'"
    )


# --------------------------------------------------------------------------
# 撤销（undo）：实体级还原（P2 金融级治理）
# --------------------------------------------------------------------------


def _row_to_json(row: aiosqlite.Row | dict[str, Any] | None) -> str:
    """快照字典序列化：None → '{}' 表示实体此前不存在（undo 时应 DELETE）。"""
    if row is None:
        return "{}"
    return json.dumps(dict(row), ensure_ascii=False, default=str)


async def _record_snapshot(
    entity: str,
    entity_id: str,
    before_json: str,
    actor: str = "",
) -> int:
    """为一次即将发生的写操作落一份前快照，供后续 undo 恢复。

    调用规范：**本函数不 commit**。上层必须在同一事务内、调用本函数继续做实际写
    操作后统一 ``await conn.commit()``——让「快照 + 写操作」原子提交，任一失败整笔回滚。

    语义：
    - before_json='{}' 代表"该实体此前不存在"，undo 时应当 DELETE 当前行；
    - before_json 为旧行 JSON 时，undo 时使用 INSERT OR REPLACE 恢复全量字段。
    """
    conn = await _conn()
    cur = await conn.execute(
        "INSERT INTO undo_records(entity,entity_id,before_json,reason,consumed_at,created_at)"
        " VALUES(?,?,?,?,?,?)",
        (
            entity,
            entity_id,
            before_json,
            actor[:500],
            "",
            _now_iso(),
        ),
    )
    return cur.lastrowid


async def _find_latest_usable_snapshot(
    conn: aiosqlite.Connection,
    entity: str,
    entity_id: str,
) -> aiosqlite.Row | None:
    """同一实体可能有多条快照，取最近一条未被撤回（consumed_at=''）的记录；没有返回 None。"""
    cur = await conn.execute(
        "SELECT * FROM undo_records"
        " WHERE entity=? AND entity_id=? AND consumed_at=''"
        " ORDER BY id DESC LIMIT 1",
        (entity, entity_id),
    )
    return await cur.fetchone()


async def _restore_from_snapshot(
    conn: aiosqlite.Connection,
    entity: str,
    entity_id: str,
    before_json: str,
) -> None:
    """按 before_json 把实体恢复成操作前状态：'{}' → DELETE，其余 → INSERT OR REPLACE。

    共享逻辑：按实体类型做列映射。所有可撤回实体都具备『单表 + 单列主键』结构，
    通过 INSERT OR REPLACE 能覆盖 update/delete 两条路径的恢复。
    """
    deleted = False
    if before_json.strip() in ("", "{}"):
        if entity == "transaction":
            await conn.execute("DELETE FROM transactions WHERE id=?", (int(entity_id),))
        elif entity == "position":
            await conn.execute("DELETE FROM positions WHERE symbol=?", (entity_id,))
        elif entity == "debt":
            await conn.execute("DELETE FROM debts WHERE name=?", (entity_id,))
        elif entity == "subscription":
            await conn.execute("DELETE FROM subscriptions WHERE name=?", (entity_id,))
        else:
            raise ValueError(f"不支持撤回的实体类型：{entity}")
        deleted = True
        _ = deleted  # 调用方如需扩展两种路径的审计日志时可直接使用
        return

    data = json.loads(before_json)
    if entity == "transaction":
        d = data.get("date")
        it = data.get("item")
        cat = data.get("category")
        amt = data.get("amount")
        if not all([d, it, cat]) or amt is None:
            raise ValueError(f"transaction 快照字段不完整：{before_json[:120]!r}")
        owner_id = data.get("owner_id") or 0
        is_shared = 1 if data.get("is_shared") else 0
        await conn.execute(
            "INSERT OR REPLACE INTO transactions(id,date,item,category,amount,owner_id,is_shared)"
            " VALUES(?,?,?,?,?,?,?)",
            (int(entity_id), d, it, cat, amt, owner_id, is_shared),
        )
    elif entity == "position":
        # 任何字段缺失用 '' / 0 兜底，避免 CHECK 失败；符号一致即满足主键；符号本身不回退
        await conn.execute(
            "INSERT OR REPLACE INTO positions(symbol,name,kind,industry,shares,cost,last,buy_date,fee)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                entity_id,
                data.get("name") or "未命名",
                data.get("kind") or "股票",
                data.get("industry") or "其他",
                data.get("shares"),
                data.get("cost"),
                data.get("last"),
                data.get("buy_date"),
                data.get("fee"),
            ),
        )
    elif entity == "debt":
        await conn.execute(
            "INSERT OR REPLACE INTO debts(name,monthly,balance,rate,due_day)"
            " VALUES(?,?,?,?,?)",
            (
                entity_id,
                data.get("monthly"),
                data.get("balance"),
                data.get("rate"),
                data.get("due_day", ""),
            ),
        )
    elif entity == "subscription":
        await conn.execute(
            "INSERT OR REPLACE INTO subscriptions(name,monthly,note,due_day)"
            " VALUES(?,?,?,?)",
            (
                entity_id,
                data.get("monthly"),
                data.get("note", ""),
                data.get("due_day", ""),
            ),
        )
    else:
        raise ValueError(f"不支持撤回的实体类型：{entity}")


async def _undo_apply(record_id: int) -> dict[str, Any]:
    """对 undo_records 中一条快照执行撤回（恢复 before_json 并标记 consumed_at）。

    在单一 aiosqlite 事务里完成：
    1. 锁定该快照（空 consumed_id → 可撤回；否则幂等拒绝 → 调用方回 410 Gone）；
    2. 按 before_json 恢复实体（'' / '{}' → DELETE，否则 INSERT OR REPLACE）；
    3. 写 undo_records.consumed_at = now()。

    """
    conn = await _conn()
    # step 0: 取快照
    cur = await conn.execute("SELECT * FROM undo_records WHERE id=?", (record_id,))
    snap = await cur.fetchone()
    if snap is None:
        raise LookupError(f"undo 记录 {record_id} 不存在")
    if snap["consumed_at"]:
        raise ValueError("already_consumed")

    entity = snap["entity"]
    entity_id = snap["entity_id"]
    before_json = snap["before_json"]

    # step 1: 恢复实体
    await _restore_from_snapshot(conn, entity, entity_id, before_json)

    # step 2: 标记 consumed_at（WHERE consumed_at='' 防止 TOCTOU）
    consumed_at = _now_iso()
    cur = await conn.execute(
        "UPDATE undo_records SET consumed_at=? WHERE id=? AND consumed_at=''",
        (consumed_at, record_id),
    )
    if cur.rowcount == 0:
        # 并发消费：另一个请求已撤回此快照
        await conn.rollback()
        raise ValueError("already_consumed")
    await conn.commit()
    return {
        "ok": True,
        "id": record_id,
        "entity": entity,
        "entity_id": entity_id,
        "consumed_at": consumed_at,
    }


async def list_undo_records(
    entity: str | None = None,
    entity_id: str | None = None,
    limit: int = 200,
    include_consumed: bool = False,
) -> list[dict[str, Any]]:
    """查询撤销快照（默认只返回未被撤回的；all=True 返回全部）。

    末尾 N 条按 id DESC（最新在前），便于前端撤回面板按时间倒序展示。
    """
    sql = "SELECT * FROM undo_records WHERE 1=1"
    params: list[Any] = []
    if not include_consumed:
        sql += " AND consumed_at=''"
    if entity:
        sql += " AND entity=?"
        params.append(entity)
    if entity_id:
        sql += " AND entity_id=?"
        params.append(entity_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(_clamp_limit(limit, default=200))
    return await fetch_all(sql, tuple(params))


# --------------------------------------------------------------------------
# 运行历史
# --------------------------------------------------------------------------


async def save_run(
    thread_id: str,
    question: str,
    answer: str,
    level: str,
    flags: list[dict[str, Any]] | None = None,
    route: str = "",
    llm: str = "",
    route_reason: str = "",
    tools: list[str] | None = None,
    actions: list[dict[str, Any]] | None = None,
    skip_session: bool = False,
) -> dict[str, Any]:
    conn = await _conn()
    created = datetime.now().astimezone().isoformat(timespec="seconds")
    cur = await conn.execute(
        "INSERT INTO runs(thread_id,question,answer,level,flags_json,created_at,route,llm,route_reason,tools,actions)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            thread_id or "default",
            question,
            answer,
            level or "",
            json.dumps(flags or [], ensure_ascii=False),
            created,
            route or "",
            llm or "",
            route_reason or "",
            json.dumps(tools or [], ensure_ascii=False),
            json.dumps(actions or [], ensure_ascii=False),
        ),
    )
    await conn.commit()
    if not skip_session:
        # 会话列表只收录真实对话；定时晨报等系统归档（thread_id='cron'）不建会话，
        # 晨报历史仍按 thread_id='cron' 从 runs 表读取，不污染「问AI」会话列表。
        await upsert_session(thread_id or "default", question)
    return {"ok": True, "id": cur.lastrowid}


async def delete_last_run(
    thread_id: str, question: str | None = None
) -> dict[str, Any]:
    """删除指定会话中某问题的最近一条问答（'重新生成'用：先移除旧回答再重答）。

    传 question 时精确匹配该问题的最近记录并删除；传了但未命中返回 deleted=0，
    绝不退化为删除线程最后一条（避免误删另一问题的回答）。未传 question 才删线程末条。
    """
    conn = await _conn()
    if question:
        cur = await conn.execute(
            "SELECT id FROM runs WHERE thread_id=? AND question=?"
            " ORDER BY id DESC LIMIT 1",
            (thread_id, question),
        )
        row = await cur.fetchone()
        if row:
            await conn.execute("DELETE FROM runs WHERE id=?", (row["id"],))
            await conn.commit()
            return {"ok": True, "deleted": 1}
        return {"ok": True, "deleted": 0}
    cur = await conn.execute(
        "SELECT id FROM runs WHERE thread_id=? ORDER BY id DESC LIMIT 1", (thread_id,)
    )
    row = await cur.fetchone()
    if row:
        await conn.execute("DELETE FROM runs WHERE id=?", (row["id"],))
        await conn.commit()
    return {"ok": True}


async def list_runs(
    thread_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    clamped = _clamp_limit(limit)
    if thread_id:
        rows = await fetch_all(
            "SELECT * FROM runs WHERE thread_id=? ORDER BY id DESC LIMIT ?",
            (thread_id, clamped),
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (clamped,)
        )
    return [_hydrate_run(r) for r in rows]


async def claim_pending_nl(thread_id: str) -> bool:
    """原子消费该线程最后一条 nl_pending run（大额审批回执，确认/取消共用）。

    单条 UPDATE + rowcount 判定：并发回执或断连重试时仅一个能 claim 成功，
    防止同一笔待确认被重复入账；claim 成功后该 run 的 route 记为 nl_pending_consumed。
    """
    conn = await _conn()
    cur = await conn.execute(
        "UPDATE runs SET route='nl_pending_consumed' "
        "WHERE id = (SELECT id FROM runs WHERE thread_id=? ORDER BY id DESC LIMIT 1) "
        "AND route='nl_pending'",
        (thread_id,),
    )
    await conn.commit()
    return cur.rowcount == 1


def _hydrate_run(r: dict[str, Any]) -> dict[str, Any]:
    """把 runs 行的 JSON 列反序列化（flags/tools/actions），返回可序列化 dict。"""
    out = dict(r)
    for col, field in (
        ("flags_json", "flags"),
        ("tools", "tools"),
        ("actions", "actions"),
    ):
        try:
            out[field] = json.loads(out.pop(col) or "[]")
        except Exception:
            out[field] = []
    return out


async def search_runs(q: str, limit: int = 50) -> list[dict[str, Any]]:
    """跨会话全文搜索历次问答（question / answer LIKE），附带所属会话标题，供全局历史跳转。"""
    # 转义 LIKE 通配符：用户输入含 % 或 _ 时按字面字符处理，不可充当通配符（防注入+DoS）
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    kw = f"%{esc}%"
    rows = await fetch_all(
        "SELECT r.*, s.title AS session_title"
        " FROM runs r LEFT JOIN sessions s ON s.thread_id = r.thread_id"
        " WHERE r.question LIKE ? ESCAPE '\\' OR r.answer LIKE ? ESCAPE '\\'"
        " ORDER BY r.id DESC LIMIT ?",
        (kw, kw, _clamp_limit(limit)),
    )
    return [_hydrate_run(r) for r in rows]


async def delete_run(run_id: int) -> dict[str, Any]:
    """删除单条历史问答记录。"""
    conn = await _conn()
    cur = await conn.execute("DELETE FROM runs WHERE id=?", (int(run_id),))
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount or 0}


async def clear_history() -> dict[str, Any]:
    """清空全部历史：删除所有会话、问答记录与会话摘要。"""
    conn = await _conn()
    await conn.execute("DELETE FROM runs")
    await conn.execute("DELETE FROM sessions")
    await conn.execute("DELETE FROM conversation_summary")
    await conn.commit()
    return {"ok": True, "cleared": True}


# --------------------------------------------------------------------------
# 会话管理（thread 列表：新建 / 重命名 / 删除）
# --------------------------------------------------------------------------


def is_system_thread(thread_id: str) -> bool:
    """系统归档线程（不属于「问AI」会话列表）：cron 晨报 / skill:<id> 技能定时触发。"""
    return thread_id == "cron" or thread_id.startswith("skill:")


async def upsert_session(thread_id: str, title: str) -> dict[str, Any]:
    """问答落库时同步会话表：标题仍为默认'新会话'时用首个问题覆盖，否则保留自定义；刷新 updated_at。

    系统归档线程直接拒绝（第三道防线：调用方应传 skip_session，读侧与启动迁移也各自排除）。
    """
    if is_system_thread(thread_id):
        return {"ok": True, "thread_id": thread_id, "skipped": "system_thread"}
    conn = await _conn()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    await conn.execute(
        "INSERT INTO sessions(thread_id,title,created_at,updated_at) VALUES(?,?,?,?)"
        " ON CONFLICT(thread_id) DO UPDATE SET"
        " title=CASE WHEN sessions.title='新会话' THEN excluded.title ELSE sessions.title END,"
        " updated_at=excluded.updated_at",
        (thread_id, title[:40] or "新会话", now, now),
    )
    await conn.commit()
    return {"ok": True, "thread_id": thread_id}


async def create_session(
    thread_id: str | None = None, title: str = "新会话"
) -> dict[str, Any]:
    conn = await _conn()
    tid = thread_id or uuid_hex()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    cur = await conn.execute(
        "INSERT INTO sessions(thread_id,title,created_at,updated_at) VALUES(?,?,?,?)",
        (tid, title[:40] or "新会话", now, now),
    )
    await conn.commit()
    return {"ok": True, "id": cur.lastrowid, "thread_id": tid}


async def list_sessions() -> list[dict[str, Any]]:
    # 读侧同样排除系统归档线程（cron 晨报 / skill:<id> 技能触发）：即使旧库已被
    # 误建，界面也不会把它们当会话展示；启动迁移会做彻底清理。
    rows = await fetch_all(
        "SELECT id, thread_id, title, created_at, updated_at"
        " FROM sessions WHERE thread_id <> 'cron' AND thread_id NOT LIKE 'skill:%'"
        " ORDER BY updated_at DESC"
    )
    return rows


async def rename_session(session_id: int, title: str) -> dict[str, Any]:
    conn = await _conn()
    await conn.execute(
        "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
        (
            str(title).strip()[:40] or "新会话",
            datetime.now().astimezone().isoformat(timespec="seconds"),
            int(session_id),
        ),
    )
    await conn.commit()
    return {"ok": True}


async def delete_session(session_id: int) -> dict[str, Any]:
    """删除会话及其全部问答记录（含长会话摘要）。"""
    conn = await _conn()
    row = await (
        await conn.execute(
            "SELECT thread_id FROM sessions WHERE id=?", (int(session_id),)
        )
    ).fetchone()
    await conn.execute("DELETE FROM sessions WHERE id=?", (int(session_id),))
    if row:
        await conn.execute("DELETE FROM runs WHERE thread_id=?", (row["thread_id"],))
        await conn.execute(
            "DELETE FROM conversation_summary WHERE thread_id=?", (row["thread_id"],)
        )
    await conn.commit()
    return {"ok": True, "deleted": True}


async def session_thread_id(session_id: int) -> str | None:
    """会话对应的 thread_id；不存在返回 None。"""
    conn = await _conn()
    row = await (
        await conn.execute(
            "SELECT thread_id FROM sessions WHERE id=?", (int(session_id),)
        )
    ).fetchone()
    return row["thread_id"] if row else None


async def move_runs(from_tid: str, to_tid: str) -> int:
    """把 from 线程下的 runs 迁到 to 线程（乐观新建会话窗口内的提问归位）。返回迁移条数。"""
    if not from_tid or from_tid == to_tid:
        return 0
    conn = await _conn()
    cur = await conn.execute(
        "UPDATE runs SET thread_id=? WHERE thread_id=?", (to_tid, from_tid)
    )
    await conn.commit()
    return cur.rowcount or 0


async def get_conversation_summary(thread_id: str) -> dict[str, Any] | None:
    """取会话压缩摘要；无则返回 None。"""
    rows = await fetch_all(
        "SELECT summary, source, covered_to, updated_at FROM conversation_summary WHERE thread_id=?",
        (thread_id,),
    )
    if not rows:
        return None
    return rows[0]


async def set_conversation_summary(
    thread_id: str, summary: str, source: str, covered_to: int
) -> dict[str, Any]:
    """写入/覆盖会话摘要（长会话压缩后的持久化上下文）。"""
    conn = await _conn()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    await conn.execute(
        "INSERT INTO conversation_summary(thread_id,summary,source,covered_to,updated_at)"
        " VALUES(?,?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET"
        " summary=excluded.summary, source=excluded.source,"
        " covered_to=excluded.covered_to, updated_at=excluded.updated_at",
        (thread_id, summary[:4000], source[:16], int(covered_to or 0), now),
    )
    await conn.commit()
    return {"ok": True}


async def clear_conversation_summary(thread_id: str) -> dict[str, Any]:
    """删除某会话摘要（会话重置/清理时用）。"""
    conn = await _conn()
    await conn.execute(
        "DELETE FROM conversation_summary WHERE thread_id=?", (thread_id,)
    )
    await conn.commit()
    return {"ok": True}


def uuid_hex() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------
# 待确认动作（写操作 HITL：确认前不落库，token 一次性消费）
# --------------------------------------------------------------------------


PENDING_TTL_MINUTES = 10


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


async def create_pending_action(
    tool_name: str, args: dict[str, Any], summary: str, lang: str = "zh"
) -> dict[str, Any]:
    """登记一个待用户确认的写类动作，返回带一次性 token 的 pending 记录。"""
    import uuid as _uuid

    token = _uuid.uuid4().hex
    now = _now_iso()
    from datetime import timedelta

    expires = (
        datetime.now().astimezone() + timedelta(minutes=PENDING_TTL_MINUTES)
    ).isoformat(timespec="seconds")
    conn = await _conn()
    await conn.execute(
        "INSERT INTO pending_actions(token,tool_name,args,summary,lang,status,created_at,expires_at)"
        " VALUES(?,?,?,?,?,'pending',?,?)",
        (
            token,
            tool_name,
            json.dumps(args, ensure_ascii=False),
            summary,
            lang,
            now,
            expires,
        ),
    )
    await conn.commit()
    return {
        "ok": True,
        "token": token,
        "tool_name": tool_name,
        "args": args,
        "summary": summary,
        "expires_at": expires,
    }


async def get_pending_action(token: str) -> dict[str, Any] | None:
    """按 token 取待确认动作；不存在/已消费/已取消/已过期一律返回 None（token 一次性）。"""
    rows = await fetch_all(
        "SELECT * FROM pending_actions WHERE token=? AND status='pending'",
        (token,),
    )
    if not rows:
        return None
    row = rows[0]
    # 惰性过期：到期未确认的标记 expired 并作废
    if str(row["expires_at"] or "") < _now_iso():
        conn = await _conn()
        await conn.execute(
            "UPDATE pending_actions SET status='expired' WHERE token=? AND status='pending'",
            (token,),
        )
        await conn.commit()
        return None
    return {
        "token": row["token"],
        "tool_name": row["tool_name"],
        "args": json.loads(row["args"] or "{}"),
        "summary": row["summary"],
        "lang": row.get("lang") or "zh",
        "expires_at": row["expires_at"],
    }


async def mark_pending_action(token: str, status: str) -> dict[str, Any]:
    conn = await _conn()
    await conn.execute(
        "UPDATE pending_actions SET status=? WHERE token=? AND status='pending'",
        (status, token),
    )
    await conn.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# 数据导出 / 月度趋势
# --------------------------------------------------------------------------


async def export_data() -> dict[str, Any]:
    """全量导出（备份）：持仓 / 流水 / 订阅 / 负债 / 预算 / 目标 / 长期记忆 / 设置 / 会话 / 问答。"""
    runs = await fetch_all("SELECT * FROM runs ORDER BY id")
    for r in runs:
        try:
            r["flags"] = json.loads(r.pop("flags_json") or "[]")
        except Exception:
            r["flags"] = []
        try:
            r["tools"] = json.loads(r.pop("tools") or "[]")
        except Exception:
            r["tools"] = []
        try:
            r["actions"] = json.loads(r.pop("actions") or "[]")
        except Exception:
            r["actions"] = []
    settings = await get_settings()
    # 备份文件可能被分享/上传：AI Key 不落明文（恢复时在设置页重新填写）
    if settings.get("ai_api_key"):
        settings["ai_api_key"] = "********"
    return {
        "version": 2,
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "positions": await list_positions(),
        "transactions": await list_transactions(),
        "subscriptions": await list_subscriptions(),
        "debts": await list_debts(),
        "budgets": await fetch_all("SELECT * FROM budgets ORDER BY month, category"),
        "goals": await fetch_all("SELECT * FROM goals ORDER BY name"),
        "memory": await fetch_all("SELECT * FROM user_memory ORDER BY id"),
        "settings": settings,
        "sessions": await list_sessions(),
        "runs": runs,
    }


async def monthly_trend(months: int = 6) -> list[dict[str, Any]]:
    """按自然月聚合流水：收入 / 支出 / 结余（含当前月，最近 N 个月）。"""
    rows = await fetch_all(
        "SELECT substr(date,1,7) AS month,"
        " SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,"
        " SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS expense,"
        " SUM(amount) AS net"
        " FROM transactions GROUP BY month ORDER BY month DESC LIMIT ?",
        (int(months),),
    )
    return [dict(r) for r in reversed(rows)]


# --------------------------------------------------------------------------
# 备份恢复（导入导出配套；AI Key 不恢复，需重新在设置页填写）
# --------------------------------------------------------------------------


async def import_backup(data: dict[str, Any]) -> dict[str, int]:
    """把 export_data() 的 JSON 恢复进库：先清空业务表再写入。

    返回各表写入条数。settings 跳过 ai_api_key（安全），其余按 key 覆盖。
    """
    conn = await _conn()
    counts: dict[str, int] = {}
    try:
        for t in (
            "positions",
            "transactions",
            "subscriptions",
            "debts",
            "budgets",
            "goals",
            "user_memory",
            "runs",
            "sessions",
        ):
            await conn.execute(f"DELETE FROM {t}")

        counts["positions"] = await _restore_table(
            conn,
            "positions",
            data.get("positions"),
            "INSERT INTO positions(symbol,name,kind,industry,shares,cost,last,buy_date,fee)"
            " VALUES(:symbol,:name,:kind,:industry,:shares,:cost,:last,:buy_date,:fee)",
        )
        counts["transactions"] = await _restore_table(
            conn,
            "transactions",
            data.get("transactions"),
            "INSERT INTO transactions(date,item,category,amount) VALUES(:date,:item,:category,:amount)",
        )
        counts["subscriptions"] = await _restore_table(
            conn,
            "subscriptions",
            data.get("subscriptions"),
            "INSERT INTO subscriptions(name,monthly,note,due_day) VALUES(:name,:monthly,:note,:due_day)",
        )
        counts["debts"] = await _restore_table(
            conn,
            "debts",
            data.get("debts"),
            "INSERT INTO debts(name,monthly,balance,rate,due_day) VALUES(:name,:monthly,:balance,:rate,:due_day)",
        )
        counts["budgets"] = await _restore_table(
            conn,
            "budgets",
            data.get("budgets"),
            "INSERT INTO budgets(month,category,amount) VALUES(:month,:category,:amount)",
        )
        counts["goals"] = await _restore_table(
            conn,
            "goals",
            data.get("goals"),
            "INSERT INTO goals(name,target,saved,deadline,created_at)"
            " VALUES(:name,:target,:saved,:deadline,:created_at)",
        )
        counts["memory"] = await _restore_table(
            conn,
            "user_memory",
            data.get("memory"),
            "INSERT INTO user_memory(content,kind,created_at,updated_at)"
            " VALUES(:content,:kind,:created_at,:updated_at)",
        )

        # 设置：整表覆盖，但 AI Key 永不恢复（明文 Key 不进备份/恢复链路）
        settings = data.get("settings") or {}
        if isinstance(settings, dict):
            await conn.execute("DELETE FROM settings")
            await conn.executemany(
                "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                [(k, str(v)) for k, v in settings.items() if k != "ai_api_key"],
            )
            await _ensure_defaults()
            await _mark_user_data(conn)
            counts["settings"] = len(settings) - (1 if "ai_api_key" in settings else 0)

        # 会话与问答历史：整体恢复（tools/flags 原样保留）
        sessions = data.get("sessions") or []
        for s in sessions:
            if not isinstance(s, dict) or not s.get("thread_id"):
                continue
            await conn.execute(
                "INSERT OR IGNORE INTO sessions(thread_id,title,created_at,updated_at)"
                " VALUES(?,?,?,?)",
                (
                    s["thread_id"],
                    str(s.get("title") or "新会话")[:40],
                    s.get("created_at") or "",
                    s.get("updated_at") or "",
                ),
            )
        counts["sessions"] = len(sessions)
        runs = data.get("runs") or []
        for r in runs:
            if not isinstance(r, dict) or not r.get("question"):
                continue
            await conn.execute(
                "INSERT INTO runs(thread_id,question,answer,level,flags_json,created_at,route,llm,route_reason,tools,actions)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    r.get("thread_id") or "default",
                    str(r.get("question") or "")[:500],
                    str(r.get("answer") or ""),
                    str(r.get("level") or ""),
                    json.dumps(r.get("flags") or [], ensure_ascii=False),
                    r.get("created_at")
                    or datetime.now().astimezone().isoformat(timespec="seconds"),
                    str(r.get("route") or ""),
                    str(r.get("llm") or ""),
                    str(r.get("route_reason") or ""),
                    json.dumps(r.get("tools") or [], ensure_ascii=False),
                    json.dumps(r.get("actions") or [], ensure_ascii=False),
                ),
            )
        counts["runs"] = len(runs)

        await conn.commit()
    except Exception:  # noqa: BLE001 — 恢复失败整体回滚，不留半截状态
        await conn.rollback()
        raise
    return counts


async def _restore_table(
    conn: aiosqlite.Connection,
    name: str,
    rows: Any,
    sql: str,
) -> int:
    """把备份列表写回指定表；坏行跳过不影响整体。"""
    if not isinstance(rows, list):
        return 0
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            await conn.execute(sql, row)
            n += 1
        except Exception:  # noqa: BLE001 — 单行失败跳过
            continue
    return n


# --------------------------------------------------------------------------
# 家庭成员 CRUD
# --------------------------------------------------------------------------

async def member_create(
    display_name: str,
    role: str = "member",
    username: str = "",
    avatar_color: str = "",
) -> int:
    """创建家庭成员，返回 id。"""
    valid_roles = {"owner", "admin", "member", "viewer"}
    if role not in valid_roles:
        role = "member"
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    uname = (username or f"member_{now.replace(':', '').replace('-', '').replace('T', '_')}")[:40]
    # 保底唯一
    base = uname
    counter = 1
    conn = await _conn()
    while True:
        row = await (await conn.execute("SELECT id FROM members WHERE username=?", (uname,))).fetchone()
        if row is None:
            break
        uname = f"{base}_{counter}"[:40]
        counter += 1
    if not avatar_color:
        # 轮转分配颜色
        cnt = await member_count()
        avatar_color = _AVATAR_COLORS[cnt % len(_AVATAR_COLORS)]
    cur = await conn.execute(
        "INSERT INTO members(username, display_name, role, avatar_color, created_at) "
        "VALUES(?,?,?,?,?)",
        (uname, display_name.strip()[:40] or "未命名", role, avatar_color, now),
    )
    await conn.commit()
    return cur.lastrowid


async def member_count() -> int:
    """家庭成员总数"""
    row = await fetch_one("SELECT COUNT(*) as cnt FROM members")
    return int(row["cnt"]) if row else 0


async def list_members() -> list[dict[str, Any]]:
    """列出所有家庭成员"""
    return await fetch_all("SELECT * FROM members ORDER BY id")


async def member_update(member_id: int, **kwargs: Any) -> dict[str, Any]:
    """修改成员信息。支持 display_name / role / avatar_color。"""
    allowed = {"display_name", "role", "avatar_color"}
    sets: list[str] = []
    vals: list[Any] = []
    for k, v in kwargs.items():
        if k not in allowed or v is None:
            continue
        if k == "role" and v not in ("owner", "admin", "member", "viewer"):
            continue
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        # 无有效修改字段，直接返回当前信息
        m = await _fetch_member(member_id)
        return m or {}
    vals.append(member_id)
    conn = await _conn()
    await conn.execute(
        f"UPDATE members SET {','.join(sets)} WHERE id=?",
        tuple(vals),
    )
    await conn.commit()
    return await _fetch_member(member_id) or {}


async def member_delete(member_id: int) -> dict[str, Any]:
    """移除成员（该成员的流水 owner_id 置 NULL，不级联删除）。"""
    conn = await _conn()
    # 软切断：该成员的流水不再归属任何人（保持流水不计丢）
    await conn.execute("UPDATE transactions SET owner_id=NULL WHERE owner_id=?", (member_id,))
    cur = await conn.execute("DELETE FROM members WHERE id=?", (member_id,))
    # 清理借贷中涉及此成员的行
    await conn.execute(
        "DELETE FROM member_loans WHERE from_member_id=? OR to_member_id=?",
        (member_id, member_id),
    )
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


# --------------------------------------------------------------------------
# 成员间借贷 CRUD
# --------------------------------------------------------------------------

async def loan_create(
    from_member_id: int,
    to_member_id: int,
    amount: float,
    note: str = "",
    currency: str = "CNY",
) -> int:
    """创建成员间借贷，返回 id。"""
    if from_member_id == to_member_id:
        raise ValueError("借贷双方不能是同一成员")
    amt = float(amount)
    if amt <= 0:
        raise ValueError("借贷金额必须大于 0")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    conn = await _conn()
    cur = await conn.execute(
        "INSERT INTO member_loans(from_member_id, to_member_id, amount, currency, note, settled, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (from_member_id, to_member_id, amt, currency, note.strip()[:200], 0, now),
    )
    await conn.commit()
    return cur.lastrowid


async def list_loans(settled: bool | None = None) -> list[dict[str, Any]]:
    """列出借贷；settled=None 全部 / True 已结 / False 未结"""
    sql = "SELECT * FROM member_loans"
    params: tuple = ()
    if settled is not None:
        sql += " WHERE settled=?"
        params = (1 if settled else 0,)
    sql += " ORDER BY created_at DESC"
    return await fetch_all(sql, params)


async def loan_settle(loan_id: int) -> dict[str, Any]:
    """结清一笔借贷"""
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    conn = await _conn()
    cur = await conn.execute(
        "UPDATE member_loans SET settled=1, settled_at=? WHERE id=?",
        (now, loan_id),
    )
    await conn.commit()
    return {"ok": True, "updated": cur.rowcount}


async def loan_delete(loan_id: int) -> dict[str, Any]:
    """删除一笔借贷"""
    conn = await _conn()
    cur = await conn.execute("DELETE FROM member_loans WHERE id=?", (loan_id,))
    await conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


# --------------------------------------------------------------------------
# 成员汇总 / 家庭仪表板
# --------------------------------------------------------------------------

async def member_summary(member_id: int) -> dict[str, Any]:
    """查询单个成员的收支汇总"""
    income = await fetch_one(
        "SELECT COALESCE(SUM(amount), 0) as val FROM transactions "
        "WHERE owner_id=? AND amount > 0 AND is_shared=1",
        (member_id,),
    )
    expense = await fetch_one(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as val FROM transactions "
        "WHERE owner_id=? AND amount < 0 AND is_shared=1",
        (member_id,),
    )
    count_row = await fetch_one(
        "SELECT COUNT(*) as val FROM transactions WHERE owner_id=?",
        (member_id,),
    )
    return {
        "member_id": member_id,
        "income": float(income["val"]) if income else 0.0,
        "expense": float(expense["val"]) if expense else 0.0,
        "transaction_count": int(count_row["val"]) if count_row else 0,
    }


async def all_members_summary() -> list[dict[str, Any]]:
    """查询所有成员的收支汇总"""
    members = await list_members()
    result = []
    for m in members:
        s = await member_summary(m["id"])
        s["display_name"] = m["display_name"]
        s["role"] = m["role"]
        s["avatar_color"] = m["avatar_color"]
        result.append(s)
    return result


async def member_outstanding_loans() -> list[dict[str, Any]]:
    """未结清借贷（附成员显示名）"""
    loans = await list_loans(settled=False)
    members = {m["id"]: m["display_name"] for m in await list_members()}
    result = []
    for ln in loans:
        result.append({
            "id": ln["id"],
            "from_member_id": ln["from_member_id"],
            "from_name": members.get(ln["from_member_id"], ""),
            "to_member_id": ln["to_member_id"],
            "to_name": members.get(ln["to_member_id"], ""),
            "amount": ln["amount"],
            "currency": ln["currency"],
            "note": ln["note"],
            "created_at": ln["created_at"],
        })
    return result


async def family_summary() -> dict[str, Any]:
    """家庭整体汇总仪表板数据"""
    # 全局统计：所有 shared=1 的流水 + owner_id=NULL 的流水（向后兼容单用户）
    income_row = await fetch_one(
        "SELECT COALESCE(SUM(amount), 0) as val FROM transactions "
        "WHERE amount > 0 AND (is_shared=1 OR owner_id IS NULL)"
    )
    expense_row = await fetch_one(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as val FROM transactions "
        "WHERE amount < 0 AND (is_shared=1 OR owner_id IS NULL)"
    )
    total_income = float(income_row["val"]) if income_row else 0.0
    total_expense = float(expense_row["val"]) if expense_row else 0.0

    # 各成员占比
    members = await list_members()
    member_stats = []
    for m in members:
        s = await member_summary(m["id"])
        member_stats.append({
            "id": m["id"],
            "display_name": m["display_name"],
            "role": m["role"],
            "avatar_color": m["avatar_color"],
            "income": s["income"],
            "expense": s["expense"],
            "balance": round(s["income"] - s["expense"], 2),
            "pct": round(s["expense"] / total_expense * 100, 1) if total_expense > 0 else 0.0,
            "transaction_count": s["transaction_count"],
        })

    # 未结清借贷
    loans = await member_outstanding_loans()

    # Top categories（本月）
    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    cat_rows = await fetch_all(
        "SELECT category, COALESCE(SUM(ABS(amount)), 0) as total "
        "FROM transactions WHERE amount < 0 AND date >= ? AND date < ? "
        "GROUP BY category ORDER BY total DESC LIMIT 5",
        (f"{month_prefix}-01", f"{month_prefix}-32"),
    )
    top_categories = [
        {"category": r["category"], "amount": round(float(r["total"]), 2)}
        for r in cat_rows
    ]

    return {
        "household_income": round(total_income, 2),
        "household_expense": round(total_expense, 2),
        "household_net": round(total_income - total_expense, 2),
        "members": member_stats,
        "outstanding_loans": loans,
        "top_categories": top_categories,
    }
