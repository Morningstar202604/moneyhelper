"""Agent 配置：角色 / skills / 工具开关；技能立即触发；AI 一键生成。

从 routes/system.py 拆出（M1.4 收尾）：原文件把 9 个互不相关的域塞在一起，
任何一个域的改动都要在 500+ 行里定位。
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..logging_utils import get_logger as _get_logger

log = _get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Agent 配置：角色 / skills / 工具开关
# ---------------------------------------------------------------------------


@router.get("/api/agent-config")
async def get_agent_config() -> dict:
    """读当前 agent 配置（角色/skills/工具）。"""
    from .. import agent_config

    cfg = await agent_config.get_config()
    return {"ok": True, "config": cfg}


@router.post("/api/agent-config")
async def update_agent_config(payload: dict) -> dict:
    """更新 agent 配置。

    保存时：非法定时动作剔除并回报 warnings；随后同步技能调度任务
    （同步失败不影响保存本身——保存是数据、排程是运行时，各自独立可恢复）。
    """
    from .. import agent_config
    from .. import scheduler as sched_mod

    new_cfg = payload.get("config", payload)
    clean, warnings = agent_config.clean_config(new_cfg)
    await agent_config.update_config(clean)
    try:
        await sched_mod.sync_skill_jobs()
    except Exception as exc:  # noqa: BLE001 — 排程失败只告警：下次保存/重启会重试
        log.warning("skill jobs sync failed after save: %s", exc)
    return {"ok": True, "warnings": warnings}


@router.post("/api/skills/{skill_id}/run")
async def run_skill_now(skill_id: str) -> dict:
    """立即触发一次技能动作（与定时触发同一实现）：走问答管线并归档，不进会话列表。"""
    from .. import scheduler as sched_mod

    try:
        return await sched_mod.run_skill_action(skill_id)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:  # noqa: BLE001 — 管线异常如实回报，不冒充成功
        log.exception("skill run failed: %s", exc)
        return JSONResponse({"ok": False, "error": f"执行失败：{exc}"}, status_code=500)


@router.post("/api/agent-config/generate")
async def generate_agent_config(payload: dict) -> dict:
    """AI 一键生成：按自然语言描述生成 skill / 角色描述（设置页「AI 生成」按钮）。

    只产出建议不落库，由用户在设置页确认后随既有保存流程写入。
    未接入模型或模型输出不可用 → 200 + {"ok": false, "error": ...}（fail-closed）。
    """
    from .. import agent_config
    from .. import llm as llm_mod

    kind = str((payload or {}).get("kind") or "skill").strip()
    prompt = str((payload or {}).get("prompt") or "").strip()
    agent_name = str((payload or {}).get("agent") or "").strip()
    if not prompt:
        return {"ok": False, "error": "请先描述你想要的效果"}
    if not await llm_mod.llm_available():
        return {
            "ok": False,
            "error": "未接入模型 —— 先到「设置 → AI 回答」配置模型端点",
        }
    suggestion = await agent_config.generate_suggestion(kind, prompt, agent_name)
    if suggestion is None:
        return {"ok": False, "error": "生成失败，请换个描述再试"}
    return {"ok": True, "suggestion": suggestion}
