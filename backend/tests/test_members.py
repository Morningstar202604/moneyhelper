"""家庭共享账本：成员管理、借贷、交易 owner 过滤、成员切换、家庭汇总。

覆盖后端家庭共享功能的全链路：
1. 成员 CRUD（创建/查询/修改/删除）
2. 成员间借贷（创建/查询/结清/删除）
3. 交易 owner 注入与可见性（shared 过滤）
4. 成员切换（活跃成员 session）
5. 家庭仪表板汇总
6. 幂等迁移验证
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

import sys
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    """独立的临时数据库 + ASGI 客户端，每个测试函数全隔离。"""
    from app import db, main

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_wealth.db")
    # 强制重置 inited 标志，让 init_db 重新执行
    db._inited = False
    db._db = None
    # 清理 active member store
    db._active_member_id.clear()
    await db.init_db()

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8787"
    ) as ac:
        yield ac

    await db.close_db()


# ---------------------------------------------------------------------------
# 1. 成员 CRUD
# ---------------------------------------------------------------------------

async def test_member_create(client):
    """创建家庭成员"""
    r = await client.post("/api/members", json={"display_name": "张三", "role": "owner"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["member"]["display_name"] == "张三"
    assert data["member"]["role"] == "owner"
    assert data["member"]["avatar_color"]  # 自动分配配色


async def test_member_create_default_role(client):
    """创建成员默认角色为 member"""
    r = await client.post("/api/members", json={"display_name": "李四"})
    assert r.status_code == 200
    assert r.json()["member"]["role"] == "member"


async def test_member_create_invalid_role(client):
    """无效角色创建失败"""
    r = await client.post("/api/members", json={"display_name": "X", "role": "superuser"})
    assert r.status_code == 400


async def test_member_create_empty_name(client):
    """显示名不能为空"""
    r = await client.post("/api/members", json={"display_name": "  ", "role": "member"})
    assert r.status_code == 400


async def test_member_list(client):
    """列出所有成员"""
    await client.post("/api/members", json={"display_name": "张三", "role": "owner"})
    await client.post("/api/members", json={"display_name": "李四", "role": "member"})
    r = await client.get("/api/members")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    names = [m["display_name"] for m in data["members"]]
    assert "张三" in names
    assert "李四" in names


async def test_member_update(client):
    """修改成员信息"""
    r = await client.post("/api/members", json={"display_name": "张三"})
    mid = r.json()["member"]["id"]
    r = await client.put(f"/api/members/{mid}", json={"display_name": "张三丰", "role": "admin"})
    assert r.status_code == 200
    assert r.json()["member"]["display_name"] == "张三丰"
    assert r.json()["member"]["role"] == "admin"


async def test_member_update_invalid_role(client):
    """修改成员为无效角色"""
    r = await client.post("/api/members", json={"display_name": "张三"})
    mid = r.json()["member"]["id"]
    r = await client.put(f"/api/members/{mid}", json={"role": "god"})
    assert r.status_code == 400


async def test_member_delete(client):
    """删除成员"""
    r = await client.post("/api/members", json={"display_name": "张三"})
    mid = r.json()["member"]["id"]
    r = await client.delete(f"/api/members/{mid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # 确认已删除
    r = await client.get("/api/members")
    assert r.json()["count"] == 0


async def test_member_delete_not_found(client):
    """删除不存在的成员"""
    r = await client.delete("/api/members/99999")
    assert r.status_code == 404


async def test_member_transactions_preserved_on_delete(client):
    """删除成员后其流水保留（owner_id 置 NULL）"""
    r = await client.post("/api/members", json={"display_name": "张三"})
    mid = r.json()["member"]["id"]
    # 添加一笔交易
    await client.post("/api/transactions", json={
        "date": "2025-01-15", "item": "测试", "category": "测试", "amount": 100,
        "owner_id": mid,
    })
    # 删除成员
    await client.delete(f"/api/members/{mid}")
    # 流水仍在
    from app import db
    txs = await db.list_transactions()
    assert len(txs) == 1
    assert txs[0]["owner_id"] is None


# ---------------------------------------------------------------------------
# 2. 成员间借贷
# ---------------------------------------------------------------------------

async def test_loan_create(client):
    """创建成员间借贷"""
    r1 = await client.post("/api/members", json={"display_name": "张三"})
    r2 = await client.post("/api/members", json={"display_name": "李四"})
    mid1 = r1.json()["member"]["id"]
    mid2 = r2.json()["member"]["id"]
    r = await client.post("/api/members/loans", json={
        "from_member_id": mid1, "to_member_id": mid2, "amount": 500, "note": "午餐",
    })
    assert r.status_code == 200
    assert r.json()["id"] > 0


async def test_loan_create_same_member(client):
    """借贷双方不能是同一成员"""
    r1 = await client.post("/api/members", json={"display_name": "张三"})
    mid = r1.json()["member"]["id"]
    r = await client.post("/api/members/loans", json={
        "from_member_id": mid, "to_member_id": mid, "amount": 100,
    })
    assert r.status_code == 400


async def test_loan_create_negative_amount(client):
    """借贷金额必须大于 0"""
    r1 = await client.post("/api/members", json={"display_name": "张三"})
    r2 = await client.post("/api/members", json={"display_name": "李四"})
    mid1 = r1.json()["member"]["id"]
    mid2 = r2.json()["member"]["id"]
    r = await client.post("/api/members/loans", json={
        "from_member_id": mid1, "to_member_id": mid2, "amount": -50,
    })
    assert r.status_code == 400


async def test_loan_settle(client):
    """结清借贷"""
    r1 = await client.post("/api/members", json={"display_name": "张三"})
    r2 = await client.post("/api/members", json={"display_name": "李四"})
    mid1 = r1.json()["member"]["id"]
    mid2 = r2.json()["member"]["id"]
    r = await client.post("/api/members/loans", json={
        "from_member_id": mid1, "to_member_id": mid2, "amount": 200,
    })
    lid = r.json()["id"]
    r = await client.post(f"/api/members/loans/{lid}/settle")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # 结清后不在未结列表
    r = await client.get("/api/members/loans?settled=false")
    assert r.json()["count"] == 0


async def test_loan_list(client):
    """列出借贷"""
    r1 = await client.post("/api/members", json={"display_name": "张三"})
    r2 = await client.post("/api/members", json={"display_name": "李四"})
    mid1 = r1.json()["member"]["id"]
    mid2 = r2.json()["member"]["id"]
    await client.post("/api/members/loans", json={
        "from_member_id": mid1, "to_member_id": mid2, "amount": 100,
    })
    r = await client.get("/api/members/loans")
    assert r.status_code == 200
    assert r.json()["count"] == 1


async def test_loan_delete(client):
    """删除借贷"""
    r1 = await client.post("/api/members", json={"display_name": "张三"})
    r2 = await client.post("/api/members", json={"display_name": "李四"})
    mid1 = r1.json()["member"]["id"]
    mid2 = r2.json()["member"]["id"]
    r = await client.post("/api/members/loans", json={
        "from_member_id": mid1, "to_member_id": mid2, "amount": 100,
    })
    lid = r.json()["id"]
    r = await client.delete(f"/api/members/loans/{lid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ---------------------------------------------------------------------------
# 3. 交易 owner 注入与可见性
# ---------------------------------------------------------------------------

async def test_transaction_inherits_active_member(client):
    """设置活跃成员后，新增交易自动归属该成员"""
    from app import db
    r = await client.post("/api/members", json={"display_name": "张三", "role": "owner"})
    mid = r.json()["member"]["id"]
    # 切换活跃成员
    await client.put("/api/members/me/switch", json={"member_id": mid})
    # 新增交易
    r = await client.post("/api/transactions", json={
        "date": "2025-01-15", "item": "记账", "category": "餐饮", "amount": -50,
    })
    assert r.status_code == 200
    # 验证 owner_id
    txs = await db.list_transactions()
    assert txs[0]["owner_id"] == mid
    # owner 角色 is_shared 自动为 1
    assert txs[0]["is_shared"] == 1


async def test_transaction_default_is_shared(client):
    """未指定 owner 时默认 is_shared=1（向后兼容单用户模式）"""
    r = await client.post("/api/transactions", json={
        "date": "2025-01-15", "item": "记账", "category": "餐饮", "amount": -50,
    })
    assert r.status_code == 200
    from app import db
    txs = await db.list_transactions()
    assert txs[0]["owner_id"] is None
    assert txs[0]["is_shared"] == 1


async def test_transaction_visibility_filter(client):
    """有 member_id 时过滤可见交易（shared=1 OR owner=自己）"""
    from app import db
    r1 = await client.post("/api/members", json={"display_name": "张三", "role": "owner"})
    r2 = await client.post("/api/members", json={"display_name": "李四", "role": "member"})
    mid1 = r1.json()["member"]["id"]
    mid2 = r2.json()["member"]["id"]

    # 张三创建一笔共享交易（owner 自动 shared）
    await client.put("/api/members/me/switch", json={"member_id": mid1})
    await client.post("/api/transactions", json={
        "date": "2025-01-15", "item": "张三共享", "category": "餐饮", "amount": -100,
    })

    # 李四创建一笔私有交易（member 默认 is_shared=0）
    await client.put("/api/members/me/switch", json={"member_id": mid2})
    await client.post("/api/transactions", json={
        "date": "2025-01-15", "item": "李四私有", "category": "餐饮", "amount": -50,
    })

    # 张三视角：shared=1 的 + 自己的 → 只能看到张三共享
    # 李四私有（is_shared=0, owner_id=mid2）不应被张三看到
    txs1 = await db.list_transactions(member_id=mid1)
    items1 = {t["item"] for t in txs1}
    assert "张三共享" in items1
    assert "李四私有" not in items1

    # 李四视角：shared=1 的 + 自己的 → 张三共享 + 李四私有
    txs2 = await db.list_transactions(member_id=mid2)
    items2 = {t["item"] for t in txs2}
    assert "张三共享" in items2
    assert "李四私有" in items2


async def test_transaction_get_endpoint(client):
    """GET /api/transactions 支持 member_id 参数"""
    await client.post("/api/transactions", json={
        "date": "2025-01-15", "item": "记账", "category": "餐饮", "amount": -50,
    })
    r = await client.get("/api/transactions")
    assert r.status_code == 200
    assert r.json()["count"] == 1


async def test_transaction_list_no_member_id(client):
    """无 member_id 时返回全部交易"""
    await client.post("/api/transactions", json={
        "date": "2025-01-15", "item": "A", "category": "餐饮", "amount": -50,
    })
    await client.post("/api/transactions", json={
        "date": "2025-01-16", "item": "B", "category": "餐饮", "amount": -30,
    })
    from app import db
    txs = await db.list_transactions(member_id=None)
    assert len(txs) == 2


# ---------------------------------------------------------------------------
# 4. 成员切换
# ---------------------------------------------------------------------------

async def test_switch_member(client):
    """切换当前活跃成员"""
    r = await client.post("/api/members", json={"display_name": "张三"})
    mid = r.json()["member"]["id"]
    r = await client.put("/api/members/me/switch", json={"member_id": mid})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["mode"] == "family"


async def test_switch_member_not_found(client):
    """切换到不存在的成员"""
    r = await client.put("/api/members/me/switch", json={"member_id": 99999})
    assert r.status_code == 404


async def test_switch_member_clear(client):
    """切换到 null 回到单用户模式"""
    r = await client.post("/api/members", json={"display_name": "张三"})
    mid = r.json()["member"]["id"]
    await client.put("/api/members/me/switch", json={"member_id": mid})
    r = await client.put("/api/members/me/switch", json={"member_id": None})
    assert r.status_code == 200
    assert r.json()["mode"] == "single"


async def test_get_current_member(client):
    """获取当前活跃成员信息"""
    # 默认无活跃成员
    r = await client.get("/api/members/me")
    assert r.status_code == 200
    assert r.json()["mode"] == "single"
    # 设置活跃成员
    r = await client.post("/api/members", json={"display_name": "张三"})
    mid = r.json()["member"]["id"]
    await client.put("/api/members/me/switch", json={"member_id": mid})
    r = await client.get("/api/members/me")
    assert r.json()["mode"] == "family"
    assert r.json()["member"]["display_name"] == "张三"


# ---------------------------------------------------------------------------
# 5. 家庭仪表板
# ---------------------------------------------------------------------------

async def test_family_summary_empty(client):
    """无成员时家庭汇总仍返回合法结构"""
    r = await client.get("/api/family/summary")
    assert r.status_code == 200
    data = r.json()
    assert "household_income" in data
    assert "household_expense" in data
    assert "household_net" in data
    assert "members" in data
    assert "outstanding_loans" in data
    assert "top_categories" in data


async def test_family_summary_with_data(client):
    """有成员和交易时的家庭汇总"""
    r1 = await client.post("/api/members", json={"display_name": "张三", "role": "owner"})
    r2 = await client.post("/api/members", json={"display_name": "李四", "role": "owner"})
    mid1 = r1.json()["member"]["id"]
    mid2 = r2.json()["member"]["id"]

    # 张三收入
    await client.post("/api/transactions", json={
        "date": "2025-01-05", "item": "工资", "category": "收入", "amount": 20000,
        "owner_id": mid1,
    })
    # 张三支出
    await client.post("/api/transactions", json={
        "date": "2025-01-10", "item": "房租", "category": "居住", "amount": -5000,
        "owner_id": mid1,
    })
    # 李四支出
    await client.post("/api/transactions", json={
        "date": "2025-01-12", "item": "餐饮", "category": "餐饮", "amount": -1500,
        "owner_id": mid2,
    })

    r = await client.get("/api/family/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["household_income"] > 0
    assert data["household_expense"] > 0
    assert len(data["members"]) == 2
    # 验证各成员 balance
    for m in data["members"]:
        if m["display_name"] == "张三":
            assert m["income"] == 20000.0
            assert m["expense"] == 5000.0
            assert m["balance"] == 15000.0


async def test_members_summary_endpoint(client):
    """获取各成员收支汇总"""
    r1 = await client.post("/api/members", json={"display_name": "张三", "role": "owner"})
    mid = r1.json()["member"]["id"]
    await client.post("/api/transactions", json={
        "date": "2025-01-05", "item": "工资", "category": "收入", "amount": 10000,
        "owner_id": mid,
    })
    r = await client.get("/api/members/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    zhang = next(m for m in data["members"] if m["display_name"] == "张三")
    assert zhang["income"] == 10000.0


# ---------------------------------------------------------------------------
# 6. 幂等 / 边界
# ---------------------------------------------------------------------------

async def test_idempotent_schema_migration(client):
    """PRAGMA table_info 迁移幂等：不报错、列存在"""
    from app import db
    cols = await db.fetch_all("PRAGMA table_info(transactions)")
    col_names = {c["name"] for c in cols}
    assert "owner_id" in col_names
    assert "is_shared" in col_names


async def test_member_unique_username(client):
    """同名成员也能创建（内部自动加后缀）"""
    r1 = await client.post("/api/members", json={"display_name": "张三", "username": "zhangsan"})
    r2 = await client.post("/api/members", json={"display_name": "张三2", "username": "zhangsan"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    members = (await client.get("/api/members")).json()["members"]
    usernames = [m["username"] for m in members]
    assert len(usernames) == len(set(usernames))


async def test_delete_member_clears_active(client):
    """删除的活跃成员被清除 session"""
    from app import db
    r = await client.post("/api/members", json={"display_name": "张三"})
    mid = r.json()["member"]["id"]
    await client.put("/api/members/me/switch", json={"member_id": mid})
    assert db.get_active_member() == mid
    await client.delete(f"/api/members/{mid}")
    # 活跃成员应被清除
    assert db.get_active_member() is None
