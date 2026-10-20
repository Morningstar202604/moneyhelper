"""组合库 + 运行历史持久化（aiosqlite，单连接串行，不阻塞事件循环）。

所有函数都是异步的；连接在启动时创建（WAL 模式）。
首次运行自动建表。全新库为**空账本**（不种示例数据）：用户从记第一笔/添加持仓开始；
示例数据仅在设置页显式"导入示例数据"时种入（演示用）。

本文件为拆分后的基础设施层：连接/建表/迁移/种子/通用查询/成员会话存储。
域数据操作见同包 users/budgets/portfolio/ledger/debts/goals/memory/audit/undo/history/backup/family。
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from ._schema import (
    DEFAULT_SETTINGS,
    SCHEMA,
    SEED_DEBTS,
    SEED_POSITIONS,
    SEED_SETTINGS,
    SEED_SUBSCRIPTIONS,
    SEED_TRANSACTIONS,
)

"""组合库 + 运行历史持久化（aiosqlite，单连接串行，不阻塞事件循环）。

所有函数都是异步的；连接在启动时创建（WAL 模式）。
首次运行自动建表。全新库为**空账本**（不种示例数据）：用户从记第一笔/添加持仓开始；
示例数据仅在设置页显式"导入示例数据"时种入（演示用）。
"""


_default_db = Path(__file__).resolve().parent.parent / "data" / "wealth.db"


def _resolve_db_path() -> Path:
    """解析数据库路径：环境变量优先，空串视为未设置（compose 的 ${VAR:-} 会注入空串）。

    空串直接交给 Path("") 会退化成当前目录，导致建库失败或写错位置，
    因此这里显式过滤空值，并展开 ~ 与相对路径。
    """
    raw = (os.getenv("XIAOMAN_DB_PATH") or "").strip()
    if not raw:
        return _default_db
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


DB_PATH = _resolve_db_path()

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
    """根据 id 取成员信息（限当前租户，防跨租户按 id 探测）"""
    from .tenant import current_user_id

    conn = await _conn()
    cur = await conn.execute(
        "SELECT id, username, display_name, role, avatar_color, created_at "
        "FROM members WHERE user_id=? AND id=?",
        (current_user_id(), member_id),
    )
    row = await cur.fetchone()
    return dict(row) if row else None




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
    await _db.execute("PRAGMA busy_timeout=5000")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.execute(
        "PRAGMA foreign_keys=ON"
    )  # SQLite 默认关外键；显式打开以启用 FK 约束/级联
    await _db.executescript(SCHEMA)
    await _migrate_add_columns()
    await _migrate_multitenant()
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


# 需要按租户隔离的表。四张"业务字段作主键"的表要重建（复合主键），
# 其余表只需加 user_id 列。
_TENANT_TABLES = (
    "transactions",
    "runs",
    "sessions",
    "budgets",
    "user_memory",
    "attachments",
    "dept_reports",
    "pending_actions",
    "undo_records",
    "member_loans",
    "members",
    "provenance_log",
    "audit_logs",
)

# 复合主键重建表：旧主键 + user_id = 新主键
_COMPOSITE_TABLES = {
    "positions": ("symbol", "TEXT PRIMARY KEY"),
    "subscriptions": ("name", "TEXT PRIMARY KEY"),
    "debts": ("name", "TEXT PRIMARY KEY"),
    "watchlist": ("symbol", "TEXT PRIMARY KEY"),
    # goals 同样用业务名作主键：两个人都有「买房」目标时必须能共存
    "goals": ("name", "TEXT PRIMARY KEY"),
    # 会话摘要按 thread_id 主键；不同用户的同名 thread 必须各存一份
    "conversation_summary": ("thread_id", "TEXT PRIMARY KEY"),
}

# 非主键但带 UNIQUE 约束的列：多租户下唯一性要按 (user_id, col) 计算
_UNIQUE_COLS = {"sessions": "thread_id"}


async def _migrate_multitenant() -> None:
    """多租户迁移：加 user_id 维度，并把历史数据归到默认租户 0。

    幂等：已经迁移过的库不会重复执行（按列存在性判断）。
    为什么四张表要重建：它们用业务字段（symbol/name）作主键，多用户下
    A 的「茅台」会覆盖 B 的「茅台」。改成 (user_id, symbol) 复合主键才能共存。
    """
    assert _db is not None

    # 1) 普通表：直接加列（SQLite 支持 ADD COLUMN 带默认值）
    for table in _TENANT_TABLES:
        cur = await _db.execute(f"PRAGMA table_info({table})")
        cols = {row["name"] for row in await cur.fetchall()}
        if not cols:
            continue  # 表不存在（老库可能缺表）
        if "user_id" not in cols:
            await _db.execute(
                f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0"
            )
    # 索引：按租户过滤是最高频查询
    for table in _TENANT_TABLES:
        try:
            await _db.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table}(user_id)"
            )
        except Exception:  # noqa: BLE001 — 表不存在时跳过
            continue

    # 2) 复合主键表：重建（SQLite 不支持改主键，只能建新表搬数据）
    for table, (key_col, _decl) in _COMPOSITE_TABLES.items():
        cur = await _db.execute(f"PRAGMA table_info({table})")
        info = await cur.fetchall()
        if not info:
            continue
        cols = {row["name"] for row in info}
        if "user_id" in cols:
            continue  # 已迁移
        await _rebuild_with_user_id(table, key_col, [r["name"] for r in info])

    # 3) 仅带 UNIQUE 约束的表（sessions.thread_id）：唯一性改为 (user_id, col)
    for table, col in _UNIQUE_COLS.items():
        cur = await _db.execute(f"PRAGMA index_list({table})")
        idx_rows = await cur.fetchall()
        # 找到该列上的唯一索引名
        unique_names: list[str] = []
        for r in idx_rows:
            if not r["unique"]:
                continue
            iinfo = await (await _db.execute(f"PRAGMA index_info({r['name']})")).fetchall()
            if [x["name"] for x in iinfo] == [col]:
                unique_names.append(str(r["name"]))
        cur = await _db.execute(f"PRAGMA table_info({table})")
        info = await cur.fetchall()
        cols = {row["name"] for row in info}
        if not info or ("user_id" in cols and not unique_names):
            continue
        await _rebuild_unique_as_composite(table, col, [r["name"] for r in info])
        for name in unique_names:
            try:
                await _db.execute(f"DROP INDEX IF EXISTS {name}")
            except Exception:  # noqa: BLE001 — 自增唯一索引不可单独删除，重建表时已去掉
                pass
        await _db.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_user_{col}"
            f" ON {table}(user_id, {col})"
        )

    await _db.commit()


async def _rebuild_unique_as_composite(
    table: str, col: str, columns: list[str]
) -> None:
    """重建表：去掉列级 UNIQUE，保留数据（唯一性由调用方补的复合唯一索引保证）。"""
    assert _db is not None
    tmp = f"{table}__uq_migrate"
    cur = await _db.execute(f"PRAGMA table_info({table})")
    info = await cur.fetchall()
    defs: list[str] = ["user_id INTEGER NOT NULL DEFAULT 0"]
    for r in info:
        name, decl = r["name"], str(r["type"] or "")
        if name == "user_id":
            continue
        if r["notnull"]:
            decl += " NOT NULL"
        if r["dflt_value"] is not None:
            decl += f" DEFAULT {r['dflt_value']}"
        if r["pk"]:
            decl += " PRIMARY KEY"
        defs.append(f"{name} {decl}".strip())
    await _db.execute(f"CREATE TABLE {tmp} (\n    {',\n    '.join(defs)}\n)")
    collist = ", ".join(c for c in columns if c != "user_id")
    await _db.execute(
        f"INSERT INTO {tmp} (user_id, {collist}) SELECT 0, {collist} FROM {table}"
    )
    await _db.execute(f"DROP TABLE {table}")
    await _db.execute(f"ALTER TABLE {tmp} RENAME TO {table}")


async def _rebuild_with_user_id(table: str, key_col: str, columns: list[str]) -> None:
    """把单主键表重建为 (user_id, 原主键) 复合主键，保留全部数据。

    用 PRAGMA 拿到的列信息重建，而不是解析原 DDL 文本：
    后者要处理注释、换行、约束顺序，容易在真实 schema 上解析错。
    """
    assert _db is not None
    tmp = f"{table}__mt_migrate"
    cur = await _db.execute(f"PRAGMA table_info({table})")
    info = await cur.fetchall()

    defs: list[str] = []
    for r in info:
        name, decl = r["name"], str(r["type"] or "")
        if r["notnull"]:
            decl += " NOT NULL"
        if r["dflt_value"] is not None:
            decl += f" DEFAULT {r['dflt_value']}"
        if name != key_col and r["pk"]:
            # 非主键列上的单列主键（理论上没有），保留其唯一性
            decl += " PRIMARY KEY"
        defs.append(f"{name} {decl}".strip())
    col_defs = ",\n    ".join(defs)
    await _db.execute(
        f"CREATE TABLE {tmp} (\n    user_id INTEGER NOT NULL DEFAULT 0,\n"
        f"    {col_defs},\n    PRIMARY KEY (user_id, {key_col})\n)"
    )
    collist = ", ".join(columns)
    await _db.execute(
        f"INSERT INTO {tmp} (user_id, {collist}) SELECT 0, {collist} FROM {table}"
    )
    await _db.execute(f"DROP TABLE {table}")
    await _db.execute(f"ALTER TABLE {tmp} RENAME TO {table}")
    await _db.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table}(user_id)"
    )


async def close_db() -> None:
    global _db, _inited, _read_conns
    if _db is not None:
        await _db.close()
    _db = None
    _inited = False
    for c in _read_conns:
        await c.close()
    _read_conns = []
    _pool_locks.clear()
    _write_locks.clear()


async def _conn() -> aiosqlite.Connection:
    if _db is None:
        await init_db()
    assert _db is not None
    return _db


# 写事务串行锁（按事件循环各自持有，理由同 _pool_locks）。
# 整库只有一条写连接：多语句事务（批量入账 / 导出导入）必须互相排他，
# 否则两个协程的 BEGIN/SAVEPOINT 会互相干扰——CI 实测表现为
# "cannot start a transaction within a transaction" 与
# "no such savepoint: add_tx_batch"（另一个协程已经 RELEASE 了同名 savepoint）。
_write_locks: dict[int, asyncio.Lock] = {}


def get_write_lock() -> asyncio.Lock:
    """取当前事件循环的写事务锁。所有多语句事务都必须持它。"""
    loop_id = id(asyncio.get_running_loop())
    lk = _write_locks.get(loop_id)
    if lk is None:
        lk = asyncio.Lock()
        _write_locks[loop_id] = lk
    return lk


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
    # 示例数据属于默认租户（0）：显式写 user_id，避免多租户列 NOT NULL 失败，
    # 也避免示例数据"漏"到某个登录用户的空间里。
    await _db.executemany(
        "INSERT INTO positions(user_id,symbol,name,kind,industry,shares,cost,last,buy_date,fee)"
        " VALUES(:user_id,:symbol,:name,:kind,:industry,:shares,:cost,:last,:buy_date,:fee)",
        [{**p, "buy_date": None, "fee": 0.0, "user_id": 0} for p in SEED_POSITIONS],
    )
    await _db.executemany(
        "INSERT INTO transactions(user_id,date,item,category,amount) VALUES(?,?,?,?,?)",
        [
            (0, _seed_date(d), item, cat, amt)
            for d, item, cat, amt in SEED_TRANSACTIONS
        ],
    )
    await _db.executemany(
        "INSERT INTO subscriptions(user_id,name,monthly,note,due_day)"
        " VALUES(:user_id,:name,:monthly,:note,:due_day)",
        [
            {**s, "due_day": s.get("due_day", ""), "user_id": 0}
            for s in SEED_SUBSCRIPTIONS
        ],
    )
    await _db.executemany(
        "INSERT INTO debts(user_id,name,monthly,balance,rate,due_day)"
        " VALUES(:user_id,:name,:monthly,:balance,:rate,:due_day)",
        [{**d, "due_day": d.get("due_day", ""), "user_id": 0} for d in SEED_DEBTS],
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
    # 启动期维护：跨租户清理系统归档线程（cron / skill:*）的会话行。
    # 这些线程本就不属于任何用户的会话列表，清理是幂等的全局操作。
    await conn.execute(
        "DELETE FROM sessions WHERE thread_id='cron' OR thread_id LIKE 'skill:%'"  # tenant: allow
    )
    # 按租户各建一份：同一 thread_id 可能属于不同用户，不能混用
    rows = await (
        await conn.execute(
            "SELECT r.user_id, r.thread_id, r.question FROM runs r"
            " WHERE r.id = (SELECT MIN(id) FROM runs x"
            "               WHERE x.thread_id = r.thread_id AND x.user_id = r.user_id)"
            "   AND r.thread_id <> 'cron' AND r.thread_id NOT LIKE 'skill:%'"
            "   AND NOT EXISTS (SELECT 1 FROM sessions s"
            "                   WHERE s.thread_id = r.thread_id AND s.user_id = r.user_id)"
        )
    ).fetchall()
    if not rows:
        await conn.commit()
        return
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for r in rows:
        await conn.execute(
            "INSERT OR IGNORE INTO sessions(user_id,thread_id,title,created_at,updated_at)"
            " VALUES(?,?,?,?,?)",
            (r["user_id"], r["thread_id"], str(r["question"])[:40] or "新会话", now, now),
        )
    await conn.commit()  # M1.3：读池时代所有写路径必须真实提交，否则读池不可见


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


# 读连接池（M1.3）：WAL 下多读者并发，写仍走 _conn 单连接串行——
# 部门模式（M3）多 agent 并行取数的地基。池在首次读取时惰性建连。
_READ_POOL_SIZE = 3
_read_conns: list[aiosqlite.Connection] = []
_rr = 0
# 锁必须按事件循环各自持有：模块级 asyncio.Lock 会绑定导入时的循环，
# 换循环（TestClient/多 worker）即 "bound to a different event loop"（CI 实测教训）
_pool_locks: dict[int, asyncio.Lock] = {}


def _get_pool_lock() -> asyncio.Lock:
    lk = _pool_locks.get(id(asyncio.get_running_loop()))
    if lk is None:
        lk = asyncio.Lock()
        _pool_locks[id(asyncio.get_running_loop())] = lk
    return lk


async def _read_conn() -> aiosqlite.Connection:
    """取一条读连接：池未满则建连（持锁防并发超建），满了轮询复用。仅供只读查询。"""
    global _rr
    async with _get_pool_lock():
        if _db is None:
            await init_db()
        if len(_read_conns) < _READ_POOL_SIZE:
            # mode=ro 物理只读：任何写语句打进读池都会立刻报错，而不是
            # 开启隐式写事务持有 RESERVED 锁把写连接锁死（M1.3 实测教训）
            c = await aiosqlite.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            c.row_factory = aiosqlite.Row
            await c.execute("PRAGMA busy_timeout=5000")
            _read_conns.append(c)
            return c
        c = _read_conns[_rr % _READ_POOL_SIZE]
        _rr += 1
        return c


async def fetch_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn = await _read_conn()
    cur = await conn.execute(sql, params)
    try:
        rows = await cur.fetchall()
    finally:
        await cur.close()  # 显式终结语句：游标悬挂会长期持有读锁（M1.3 教训）
    return [dict(r) for r in rows]


async def fetch_one(sql: str, params: tuple = ()) -> aiosqlite.Row | None:
    """执行查询并返回单行结果（无匹配返回 None）。"""
    conn = await _read_conn()
    cur = await conn.execute(sql, params)
    try:
        row = await cur.fetchone()
        await cur.fetchall()  # 耗尽游标终结语句，释放读锁
        return row
    finally:
        await cur.close()


async def execute(sql: str, params: tuple = ()) -> None:
    """执行写语句（INSERT/UPDATE/DELETE）并提交。"""
    conn = await _conn()
    await conn.execute(sql, params)
    await conn.commit()


async def list_positions() -> list[dict[str, Any]]:
    # 租户过滤：只返回当前用户的持仓（默认租户 0 = 未启用登录的本机用户）
    from .tenant import current_user_id

    return await fetch_all(
        "SELECT * FROM positions WHERE user_id=? ORDER BY symbol",
        (current_user_id(),),
    )


async def list_transactions(member_id: int | None = None) -> list[dict[str, Any]]:
    """列出交易流水。

    - member_id=None：返回当前租户的全部流水
    - member_id=0 or specific id：返回 shared=1 的流水 + 自己拥有的流水
    """
    from .tenant import current_user_id

    uid = current_user_id()
    if member_id is None:
        return await fetch_all(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY date DESC, id DESC",
            (uid,),
        )
    # 有 member_id：共享流水 + 自己的流水（含私有）
    return await fetch_all(
        "SELECT * FROM transactions WHERE user_id=? AND (is_shared=1 OR owner_id=?) "
        "ORDER BY date DESC, id DESC",
        (uid, member_id),
    )


async def list_subscriptions() -> list[dict[str, Any]]:
    from .tenant import current_user_id

    return await fetch_all(
        "SELECT * FROM subscriptions WHERE user_id=? ORDER BY name",
        (current_user_id(),),
    )


async def list_debts() -> list[dict[str, Any]]:
    from .tenant import current_user_id

    return await fetch_all(
        "SELECT * FROM debts WHERE user_id=? ORDER BY name", (current_user_id(),)
    )


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
