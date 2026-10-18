"""系统域路由：认证 / 健康 / 指标 / 引导 / 记忆 / 反思 / 审计 / 附件 / 日志 /
Agent 配置 / 技能 / 晨报 / 调度器 / 数据导出导入。

从 main.py 拆出（M1.4）。鉴权由 main.py 的 api_auth 中间件统一覆盖。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .. import auth, backup, db, llm, scheduler
from ..logging_utils import clear_logs, read_log_lines
from ..logging_utils import get_logger as _get_logger
from ..middleware import metrics_body
from .settings import _mask_secret

log = _get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# 用户认证（JWT + bcrypt）
# ---------------------------------------------------------------------------


@router.post("/api/auth/register")
async def api_register(req: auth.RegisterReq):
    return await auth.register(req)


@router.post("/api/auth/login")
async def api_login(req: auth.LoginReq, request: Request):
    return await auth.login(req, request)


@router.get("/api/auth/me")
async def api_me(user: dict = Depends(auth.require_user)):
    return await auth.me(user)


@router.get("/api/auth/user-count")
async def api_user_count():
    return {"count": await db.user_count()}


# ---------------------------------------------------------------------------
# 健康 / 指标
# ---------------------------------------------------------------------------


async def _llm_model() -> str:
    try:
        s = await db.get_settings()
        return (s.get("ai_model") or "").strip() or os.getenv("LLM_MODEL", "")
    except Exception:  # noqa: BLE001
        return os.getenv("LLM_MODEL", "")


@router.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "llm_configured": await llm.llm_available(),
        "model": await _llm_model(),
    }


@router.get("/api/metrics")
async def metrics():
    return metrics_body()


# ---------------------------------------------------------------------------
# 引导（bootstrap）与模型目录
# ---------------------------------------------------------------------------


def _enabled_model_list(settings: dict[str, str]) -> list[str]:
    """把设置里的逗号分隔模型串解析成列表（只留目录内合法项，供前端用）。"""
    raw = str(settings.get("enabled_models") or "").strip()
    if not raw:
        return llm.default_enabled_models()
    catalog = {m["model"] for m in llm.model_catalog()}
    return [x for x in (s.strip() for s in raw.split(",")) if x and x in catalog]


@router.get("/api/bootstrap")
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


# ---------------------------------------------------------------------------
# 审计日志（P2 金融级治理）
# ---------------------------------------------------------------------------


@router.get("/api/audit")
async def audit_logs(limit: int = 200, action: str | None = None) -> dict:
    return {"audit": await db.list_audit_logs(limit, action)}


@router.post("/api/audit/clear")
async def clear_audit_logs() -> dict:
    return await db.clear_audit_logs()


# ---------------------------------------------------------------------------
# 附件（P2 能力扩展）：上传 / 列出 / 删除
# ---------------------------------------------------------------------------


@router.get("/api/attachments")
async def attachments(limit: int = 50) -> dict:
    return {"attachments": await db.list_attachments(limit)}


@router.post("/api/attachments")
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


@router.delete("/api/attachments/{att_id}")
async def remove_attachment(att_id: int) -> dict:
    return await db.delete_attachment(att_id)


# ---------------------------------------------------------------------------
# 数据导出 / 导入恢复 / CSV 导出
# ---------------------------------------------------------------------------


@router.get("/api/export")
async def export_data(passphrase: str | None = None) -> dict:
    """全量导出：无口令 → 明文 JSON（兼容旧版）；有口令 → 加密备份包（推荐）。"""
    data = await db.export_data()
    _mask_secret(data.get("settings", {}))
    if passphrase:
        return backup.encrypt_export(data, passphrase)
    return data


@router.post("/api/import/backup")
async def import_backup(payload: dict) -> dict:
    """从 /api/export 的 JSON 恢复全量数据（AI Key 除外，需重新填写）。

    加密备份包（encrypted=true）必须携带 passphrase 字段，口令错误会拒绝并回滚。
    """
    from ..quotes import invalidate_quotes_cache

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


@router.get("/api/export/csv")
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


# ---------------------------------------------------------------------------
# 晨报 / 调度器 / 定时产出收件箱
# ---------------------------------------------------------------------------


@router.get("/api/reports")
async def reports(limit: int = 20) -> dict:
    return {"reports": await db.list_runs("cron", limit)}


@router.post("/api/reports/generate")
async def generate_report_now() -> dict:
    try:
        result = await scheduler.generate_report()
    except Exception as exc:  # noqa: BLE001 — 手动触发失败要给可读错误
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    if result.get("skipped"):
        # 空库不生成（前端据此提示「还没有数据」而非假装成功）
        return {"ok": True, "skipped": True, "reason": result.get("reason", "no_data")}
    return {"ok": True, "answer": result["answer"], "level": result["level"]}


@router.get("/api/scheduler")
async def scheduler_status() -> dict:
    return scheduler.status()


@router.get("/api/scheduled-outputs")
async def scheduled_outputs(limit: int = 30) -> dict:
    """定时产出统一收件箱：晨报 + 技能触发合并时间线（最新在前）。

    每项带 kind（report/skill）与 skill_id/skill_name（技能产出时解析）；
    与「问AI」会话列表隔离（这些线程不建会话行），此处是它们的统一可见入口。
    """
    from .. import agent_config

    runs = await db.list_scheduled_runs(limit)
    cfg = await agent_config.get_config()
    skills = cfg.get("skills") or {}
    items: list[dict] = []
    for r in runs:
        tid = str(r.get("thread_id") or "")
        if tid == "cron":
            items.append({**r, "kind": "report", "skill_id": None, "skill_name": None})
        else:
            sid = tid.split(":", 1)[1] if ":" in tid else tid
            skill = skills.get(sid) or {}
            items.append(
                {
                    **r,
                    "kind": "skill",
                    "skill_id": sid,
                    "skill_name": str(skill.get("name") or sid),
                }
            )
    return {"outputs": items}


# ---------------------------------------------------------------------------
# 日志查看接口
# ---------------------------------------------------------------------------


@router.get("/api/logs")
async def get_logs(limit: int = 200) -> dict:
    """返回日志文件最近 limit 行（从尾部），供前端日志页使用。"""
    lines = read_log_lines(min(max(1, limit), 1000))
    return {"lines": lines, "total": len(lines)}


@router.post("/api/logs/clear")
async def clear_logs_endpoint() -> dict:
    """清空日志文件，返回清空前行数。"""
    cleared = clear_logs()
    log.info("logs cleared manually (%d lines removed)", cleared)
    return {"ok": True, "cleared_lines": cleared}


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


# vault 初始化检查（lifespan 用），保持公开以便 main.py 引用
__all__ = ["_enabled_model_list", "_llm_model", "router"]
