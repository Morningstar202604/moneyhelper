"""专家评审 P0 项的回归测试。

每条对应一个真实缺陷，且都是"顺利路径全绿、异常路径全崩"的类型：
1. ledger 编辑/合并 SQL 参数个数（多租户改造时漏加实参）
2. reset_to_seed 跨租户清库 + 无鉴权
3. settings / budgets / members 租户隔离
4. 注册（passlib × bcrypt 5 不兼容）
5. 迁移备份在 WAL 下为空 / 备份失败仍继续
6. 迁移中断后启动即死
7. 备份恢复的外键顺序（成员必须先于流水）
8. 审计写入不得提交调用方未完成的事务
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from app import db
from app.db.tenant import use_user

# ---------------------------------------------------------------------------
# P0-8：编辑 / 合并流水的 SQL 参数必须匹配
# ---------------------------------------------------------------------------


async def test_update_transaction_works(temp_db) -> None:
    """编辑流水（此前 SQL 有 2 个占位符却只传 1 个实参，必抛 ProgrammingError）。"""
    await db.add_transaction("2026-10-01", "原始", "餐饮", -30)
    tx = (await db.list_transactions())[0]
    out = await db.update_transaction(int(tx["id"]), amount=-45, item="改名")
    assert out["ok"] is True
    row = (await db.list_transactions())[0]
    assert row["amount"] == -45 and row["item"] == "改名"


async def test_merge_transactions_works(temp_db) -> None:
    """合并同类流水（此前 3 处 SQL 参数不匹配）。"""
    await db.execute("DELETE FROM transactions")
    # merge 按 (date,item,category) 分组，必须同一天同项目才会合并
    for d, item, cat, amt in (
        ("2026-10-01", "早餐", "餐饮", -10),
        ("2026-10-01", "早餐", "餐饮", -20),
    ):
        await db.add_transaction(d, item, cat, amt)
    out = await db.merge_transactions("2026-10")
    assert out["ok"] is True
    rows = [r for r in await db.list_transactions() if r["item"] == "早餐"]
    assert len(rows) == 1 and rows[0]["amount"] == -30


# ---------------------------------------------------------------------------
# P0-5：reset 只清当前租户
# ---------------------------------------------------------------------------


async def test_reset_does_not_wipe_other_tenants(temp_db) -> None:
    with use_user(11):
        await db.add_position(
            {"symbol": "000011", "name": "租户11持仓", "shares": 1, "cost": 1, "last": 1}
        )
    with use_user(22):
        await db.add_position(
            {"symbol": "000022", "name": "租户22持仓", "shares": 2, "cost": 2, "last": 2}
        )

    with use_user(11):
        await db.reset_to_seed()

    with use_user(22):
        rows = await db.list_positions()
        assert any(r["name"] == "租户22持仓" for r in rows), "reset 抹掉了其他租户的数据"
    with use_user(11):
        assert len(await db.list_positions()) > 1, "reset 没有种入示例数据"


# ---------------------------------------------------------------------------
# P0-6：settings / budgets / members 的租户隔离
# ---------------------------------------------------------------------------


async def test_settings_isolated_between_tenants(temp_db) -> None:
    with use_user(1):
        await db.set_setting("monthly_income", "11111")
    with use_user(2):
        await db.set_setting("monthly_income", "22222")
    with use_user(1):
        assert (await db.get_settings())["monthly_income"] == "11111"
    with use_user(2):
        assert (await db.get_settings())["monthly_income"] == "22222"


async def test_budgets_isolated_between_tenants(temp_db) -> None:
    with use_user(1):
        await db.save_budgets("2026-10", [{"category": "餐饮", "amount": 1000}])
    with use_user(2):
        # 同月同分类在不同租户下必须都能存（此前复合主键不含 user_id）
        await db.save_budgets("2026-10", [{"category": "餐饮", "amount": 2000}])
    with use_user(1):
        rows = await db.list_budgets("2026-10")
        assert rows and float(rows[0]["amount"]) == 1000
    with use_user(2):
        rows = await db.list_budgets("2026-10")
        assert rows and float(rows[0]["amount"]) == 2000


async def test_members_same_username_allowed_across_tenants(temp_db) -> None:
    with use_user(1):
        await db.member_create(display_name="妈妈", username="mom", role="member")
    with use_user(2):
        # 同用户名在另一个租户下必须允许（唯一性按租户）
        mid = await db.member_create(display_name="妈妈", username="mom", role="member")
        assert mid > 0


# ---------------------------------------------------------------------------
# P0-4：注册 / 登录可用（bcrypt 5）
# ---------------------------------------------------------------------------


async def test_password_hash_and_verify_roundtrip() -> None:
    from app.db.users import _hash_password, _verify_password

    h = _hash_password("password12345")
    assert h.startswith("$2b$")
    assert _verify_password("password12345", h) is True
    assert _verify_password("wrong-password", h) is False


async def test_register_and_login_via_api(temp_db) -> None:
    from app.main import app
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1:8787"
    ) as c:
        r = await c.post(
            "/api/auth/register",
            json={"username": "reguser", "password": "password12345"},
        )
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        me = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200 and me.json()["username"] == "reguser"
        lg = await c.post(
            "/api/auth/login",
            json={"username": "reguser", "password": "password12345"},
        )
        assert lg.status_code == 200


# ---------------------------------------------------------------------------
# P0-1 / P0-2 / P0-3：迁移安全
# ---------------------------------------------------------------------------


def _make_legacy_db(path: Path) -> None:
    """构造一个"旧版"库（无 user_id、业务字段作主键）。"""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE positions (
            symbol TEXT PRIMARY KEY, name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT '股票', industry TEXT NOT NULL DEFAULT '其他',
            shares REAL NOT NULL, cost REAL NOT NULL, last REAL NOT NULL,
            buy_date TEXT, fee REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE budgets (
            month TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL,
            PRIMARY KEY (month, category)
        );
        INSERT INTO positions(symbol,name,shares,cost,last) VALUES('600519','茅台',100,1680,1521);
        INSERT INTO settings(key,value) VALUES('monthly_income','24800');
        INSERT INTO budgets(month,category,amount) VALUES('2026-10','餐饮',1000);
        """
    )
    conn.commit()
    conn.close()


async def test_migration_backup_is_consistent_under_wal(tmp_path, monkeypatch) -> None:
    """WAL 模式下迁移备份必须是完整可读的库（copy2 会得到空库）。"""
    db_file = tmp_path / "legacy.db"
    _make_legacy_db(db_file)
    monkeypatch.setattr(db._core, "DB_PATH", db_file)
    await db.close_db()
    await db.init_db()
    try:
        backups = list(tmp_path.glob("legacy.db.pre-mt-*"))
        assert backups, "没有生成迁移前备份"
        c = sqlite3.connect(backups[0])
        n = c.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        assert n == 1, f"备份里数据不完整（WAL 未 checkpoint）：{n}"
        c.close()
    finally:
        await db.close_db()


async def test_half_migrated_db_is_repaired(tmp_path, monkeypatch) -> None:
    """有 user_id 列但主键仍是单列（半迁移）时必须被识别并重建。"""
    import tempfile

    work = Path(tempfile.mkdtemp(prefix="half-mt-"))
    db_file = work / "half.db"
    _make_legacy_db(db_file)
    conn = sqlite3.connect(db_file)
    # 模拟"只加了列、没重建表"的半迁移状态（先确认列不存在，保持可重跑）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(positions)")}
    if "user_id" not in cols:
        conn.execute(
            "ALTER TABLE positions ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db._core, "DB_PATH", db_file)
    await db.close_db()
    await db.init_db()
    try:
        info = await db.fetch_all("PRAGMA table_info(positions)")
        pk = [r["name"] for r in info if r["pk"]]
        assert pk == ["user_id", "symbol"], f"半迁移库未被修复，主键仍是 {pk}"
    finally:
        await db.close_db()


async def test_stale_temp_table_does_not_block_startup(tmp_path, monkeypatch) -> None:
    """迁移中断留下的临时表不能让下次启动直接失败。"""
    db_file = tmp_path / "stale.db"
    _make_legacy_db(db_file)
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE positions__mt_migrate (user_id INTEGER, symbol TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(db._core, "DB_PATH", db_file)
    await db.close_db()
    await db.init_db()  # 不应抛 "table already exists"
    try:
        assert await db.list_positions() is not None
    finally:
        await db.close_db()


# ---------------------------------------------------------------------------
# P0-7：备份恢复的外键顺序
# ---------------------------------------------------------------------------


async def test_backup_restore_keeps_owner_transactions(temp_db) -> None:
    """带 owner_id 的流水在恢复后必须仍在（此前因 FK 顺序被静默丢弃）。"""
    mid = await db.member_create(display_name="小明", username="ming", role="owner")
    await db.add_transaction("2026-10-01", "成员消费", "餐饮", -20, owner_id=mid)
    backup = await db.export_data()

    await db.execute("DELETE FROM transactions")
    await db.execute("DELETE FROM member_loans")
    await db.execute("DELETE FROM members")
    counts = await db.import_backup(backup)

    assert counts["transactions"] >= 1, "恢复时流水被丢弃"
    rows = await db.list_transactions()
    assert any(r["item"] == "成员消费" for r in rows), "带 owner 的流水没有恢复"
    members = await db.list_members()
    assert any(m["username"] == "ming" for m in members), "成员没有恢复"


async def test_backup_restore_reports_failure_instead_of_swallowing(temp_db) -> None:
    """坏数据不能让恢复"假装成功"。"""
    backup = {
        "version": 3,
        "positions": [{"symbol": None, "name": "坏行", "shares": 1, "cost": 1, "last": 1}],
    }
    with pytest.raises(ValueError, match="恢复 positions"):
        await db.import_backup(backup)


# ---------------------------------------------------------------------------
# P0-9：审计写入不提交他人事务
# ---------------------------------------------------------------------------


async def test_audit_write_does_not_commit_caller_transaction(temp_db) -> None:
    """审计写入必须与调用方事务隔离。

    构造：开启一个事务插入流水（不提交）→ 写审计 → 回滚；
    流水不应因审计的 commit 而留存。
    """
    from app.db.audit import add_audit_log

    conn = await db._conn()
    await conn.execute("BEGIN")
    await conn.execute(
        "INSERT INTO transactions(user_id,date,item,category,amount)"
        " VALUES(0,'2026-10-09','未提交流水','餐饮',-1)"
    )
    await add_audit_log(action="WRITE", method="POST", path="/x", status=200)
    await conn.rollback()

    rows = await db.fetch_all(
        "SELECT * FROM transactions WHERE item='未提交流水'"
    )
    assert rows == [], "审计写入把调用方未提交的事务提交了"
