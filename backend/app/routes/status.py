"""健康检查与指标：/api/health、/api/metrics、/api/bootstrap、模型目录。

从 routes/system.py 拆出（M1.4 收尾）：原文件把 9 个互不相关的域塞在一起，
任何一个域的改动都要在 500+ 行里定位。
"""

from __future__ import annotations

import os

from fastapi import APIRouter

from .. import db, llm, scheduler
from ..middleware import metrics_body
from .settings import _mask_secret

router = APIRouter()


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
