"""数据可移植域：全量导出/导入/月度趋势。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite

from ._core import (  # noqa: F401
    _conn,
    _ensure_defaults,  # noqa: F401
    _mark_user_data,
    fetch_all,
    get_settings,
    get_write_lock,
    list_debts,
    list_positions,
    list_subscriptions,
    list_transactions,
)
from .history import list_sessions

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
    # 多语句事务（先清表再逐表写入）：与批量入账共用写锁串行，
    # 否则并发写会在共享连接上互相破坏事务边界。
    async with get_write_lock():
        await _import_backup_locked(conn, data, counts)
    return counts


async def _import_backup_locked(
    conn: aiosqlite.Connection, data: dict[str, Any], counts: dict[str, int]
) -> None:
    """import_backup 的实际写入段（调用方必须已持有写锁）。"""
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
