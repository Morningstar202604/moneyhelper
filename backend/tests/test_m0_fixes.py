"""M0 修复回归测试：P1×3 + P2×2 的行为锁定。"""
from __future__ import annotations

import pytest


# --- P1-2: 多笔记账原子性 ---
async def test_batch_all_or_nothing(temp_db, monkeypatch):
    """第 N 条写库失败时，前面已"插入"的条目必须回滚（真实原子）。"""
    from app import db

    entries = [
        {"date": "2026-01-01", "item": "早餐", "category": "餐饮", "amount": -12.0},
        {"date": "2026-01-02", "item": "午餐", "category": "餐饮", "amount": -30.0},
        {"date": "2026-13-40", "item": "脏日期", "category": "其他", "amount": -1.0},  # 校验失败
    ]
    with pytest.raises(ValueError):
        await db.add_transactions_batch(entries)
    rows = await db.fetch_all("SELECT * FROM transactions WHERE item IN ('早餐','午餐')")
    assert rows == [], "校验失败的批次必须一条都不入库"


async def test_batch_success_writes_all(temp_db):
    from app import db

    out = await db.add_transactions_batch([
        {"date": "2026-01-01", "item": "早餐", "category": "餐饮", "amount": -12.0},
        {"date": "2026-01-02", "item": "工资", "category": "收入", "amount": 8000.0},
    ])
    assert [r["ok"] for r in out] == [True, True] and len({r["id"] for r in out}) == 2
    rows = await db.fetch_all("SELECT * FROM transactions WHERE item IN ('早餐','工资') ORDER BY id")
    assert [r["item"] for r in rows] == ["早餐", "工资"]


async def test_single_entry_still_works(temp_db):
    """旧路径（单笔 add_transaction）不受批量改造影响。"""
    from app import db

    r = await db.add_transaction("2026-01-01", "晚餐", "餐饮", -25.0)
    assert r["ok"] is True


# --- P2: 限流首请求计数 ---
def test_rate_limit_counts_first_request(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "_RATE_LIMIT_ENABLED", True)
    ip = "203.0.113.77"
    main._rate_buckets.pop(ip, None)
    ok1, _ = main._rate_limit_check(ip)
    assert ok1 is True
    # 首个请求必须已计数：窗口内再打满 MAX-1 次即触发限流
    for _ in range(main._RATE_LIMIT_MAX - 1):
        ok, retry = main._rate_limit_check(ip)
    assert ok is False and retry >= 1


# --- P1-1: litellm 键名（防再次写错：反射断言源码契约） ---
def test_litellm_chat_uses_key_field():
    import inspect

    from app import llm

    src = inspect.getsource(llm.litellm_chat)
    assert 'cfg.get("api_key")' not in src, "配置键名必须是 key（与 _config 返回结构一致）"
    assert 'cfg.get("key")' in src
