"""组合库 + 运行历史持久化（aiosqlite，单连接串行，不阻塞事件循环）。

所有函数都是异步的；连接在启动时创建（WAL 模式）。
首次运行自动建表。全新库为**空账本**（不种示例数据）：用户从记第一笔/添加持仓开始；
示例数据仅在设置页显式"导入示例数据"时种入（演示用）。

本文件为拆分后的基础设施层：连接/建表/迁移/种子/通用查询/成员会话存储。
域数据操作见同包 users/budgets/portfolio/ledger/debts/goals/memory/audit/undo/history/backup/family。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

"""组合库 + 运行历史持久化（aiosqlite，单连接串行，不阻塞事件循环）。

所有函数都是异步的；连接在启动时创建（WAL 模式）。
首次运行自动建表。全新库为**空账本**（不种示例数据）：用户从记第一笔/添加持仓开始；
示例数据仅在设置页显式"导入示例数据"时种入（演示用）。
"""


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
    "#b8891f",
    "#2e7d32",
    "#1565c0",
    "#6a1b9a",
    "#c62828",
    "#00838f",
    "#ef6c00",
    "#37474f",
    "#ad1457",
    "#3949ab",
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
        "FROM members WHERE id=?",
        (member_id,),
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
    await _db.execute(
        "PRAGMA foreign_keys=ON"
    )  # SQLite 默认关外键；显式打开以启用 FK 约束/级联
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


_COUNT_ALLOWED_TABLES = frozenset(
    {
        "transactions",
        "positions",
        "budgets",
        "goals",
        "subscriptions",
        "members",
        "runs",
        "audit_log",
        "transactions_fts",
    }
)
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


# 预算口径排除项：投资/还款属于储蓄或资金转移，不是消费支出，不计入预算使用
NON_CONSUMPTION_CATEGORIES: tuple[str, ...] = ("投资", "还款")


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


def uuid_hex() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------
# 待确认动作（写操作 HITL：确认前不落库，token 一次性消费）
# --------------------------------------------------------------------------


PENDING_TTL_MINUTES = 10


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
