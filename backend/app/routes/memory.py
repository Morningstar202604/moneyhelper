"""长期记忆与经验库（reflections）：列出 / 新增 / 删除 / 清空 / 遗忘 / AI 归纳。

从 routes/system.py 拆出（M1.4 收尾）：原文件把 9 个互不相关的域塞在一起，
任何一个域的改动都要在 500+ 行里定位。
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import db, llm

router = APIRouter()


# ---------------------------------------------------------------------------
# 长期记忆（user_memory）
# ---------------------------------------------------------------------------


@router.get("/api/memory")
async def memory_list() -> dict:
    return {"memory": await db.list_memory()}


@router.post("/api/memory")
async def create_memory(payload: dict) -> dict:
    try:
        out = await db.add_memory(str((payload or {}).get("content") or "").strip())
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)
    return out


@router.delete("/api/memory/{mem_id}")
async def remove_memory(mem_id: int) -> dict:
    return await db.delete_memory(mem_id)


@router.post("/api/memory/clear")
async def clear_memory() -> dict:
    return await db.clear_memory()


@router.post("/api/memory/forget")
async def forget_memory(payload: dict) -> dict:
    """主动遗忘：清理超过 N_used 天未使用的记忆。默认 180 天。"""
    try:
        days = max(1, min(3650, int((payload or {}).get("older_than_days") or 180)))
    except (TypeError, ValueError):
        days = 180
    deleted = await db.forget_memory(days)
    stale = await db.stale_memory_count(days)
    return {"ok": True, "deleted": deleted["deleted"], "still_stale": stale}


@router.post("/api/memory/suggest")
async def suggest_memories() -> dict:
    """AI 归纳用户偏好：看最近提问 + 现有记忆，建议 3-5 条值得长期记住的条目。

    只出建议不落库；前端逐条「记住」时才写。未接入模型 / 数据不足时友好报错。
    """
    if not await llm.llm_available():
        return {
            "ok": False,
            "error": "未接入模型 —— 先到「设置 → AI 回答」配置模型端点",
        }

    runs = await db.list_runs(None, 60)
    questions: list[str] = []
    for r in runs:
        q = str(r.get("question") or "").strip()
        if q and q not in questions:
            questions.append(q)
    if not questions:
        return {"ok": False, "error": "还没有足够的对话记录，先聊几句再来"}

    existing = await db.list_memory()
    existing_text = "；".join(str(m.get("content") or "") for m in existing[:20])
    summary = "用户最近问过：" + "；".join(questions[:25])
    if existing_text:
        summary += f"\n已记住的内容（不要重复建议）：{existing_text}"

    system = (
        "你是用户的长期记忆整理助手。根据用户最近的提问，归纳 3-5 条值得长期记住的"
        "偏好、背景或关注点（如职业、投资风格、家庭结构、常用目标），用于以后回答时参考。"
        '只输出 JSON：{"suggestions": ["条目1", "条目2", ...]}。'
        "条目以「用户」开头、每条约 15-40 字、必须是可从提问推断的事实或偏好，不要编造具体数字。"
    )
    out = await llm.json_complete(system, summary, timeout=25.0)
    if not isinstance(out, dict):
        return {"ok": False, "error": "生成失败，请稍后重试"}
    raw = out.get("suggestions")
    if not isinstance(raw, list):
        return {"ok": False, "error": "生成结果不可用，请重试"}
    items = [str(s).strip()[:80] for s in raw if str(s).strip()]
    # 去重 + 剔除与现有记忆重复的
    seen = set(existing_text.split("；")) if existing_text else set()
    uniq: list[str] = []
    for it in items:
        if it in uniq or it in seen:
            continue
        uniq.append(it)
    if not uniq:
        return {"ok": False, "error": "没有归纳出新的偏好，再聊几句试试"}
    return {
        "ok": True,
        "suggestions": uniq[:5],
        "based_on": {"questions": len(questions)},
    }


# ---------------------------------------------------------------------------
# 经验库（reflections：P1 反思/踩坑复盘）
# ---------------------------------------------------------------------------


@router.get("/api/reflections")
async def reflections(limit: int = 50) -> dict:
    return {"reflections": await db.list_reflections(limit)}


@router.post("/api/reflections")
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


@router.post("/api/reflections/{ref_id}/resolve")
async def resolve_reflection(ref_id: int) -> dict:
    return await db.resolve_reflection(ref_id)


@router.post("/api/reflections/clear")
async def clear_reflections() -> dict:
    return await db.clear_reflections()
