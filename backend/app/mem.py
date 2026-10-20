"""长记忆层：完全本地，零外部服务、零网络外发。

设计取舍：
- 记忆内容属于个人隐私，任何 embedding / 抽取请求都不能离开本机；
- 因此不做向量检索，直接用本地 BM25（rank-bm25）对 `user_memory` 表打分；
- 记忆的写入由对话内的「记住…」规则与工具触发，落库即生效，无后台管线。

与旧实现的区别：旧版用 mem0 + chromadb，且 embedder 配置为 OpenAI，
记忆内容会被发到外部端点，与「数据 100% 本地」的承诺冲突。

用法：
    from .mem import remember, recall
    await remember("下个月房租 5000")
    hits = await recall("有什么固定支出")
"""

from __future__ import annotations

from typing import Any

from .logging_utils import get_logger

log = get_logger(__name__)


async def remember(text: str) -> bool:
    """存一条长期记忆。落库成功返回 True。"""
    content = (text or "").strip()
    if not content:
        return False
    from . import db

    try:
        await db.add_memory(content, kind="fact")
        return True
    except Exception as e:  # noqa: BLE001 — 记忆写入失败不影响主回答
        log.warning("mem.remember_failed: %s", e)
        return False


async def recall(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """按 query 检索相关记忆，返回 [{memory, score}]。

    统一返回形状，调用方（agent 注入、设置页列表）无需关心底层检索方式。
    """
    from . import db

    q = (query or "").strip()
    try:
        rows = await db.list_memory()
        if q:
            rows = db.memory_retrieve(q, rows, top_k=limit)
    except Exception as e:  # noqa: BLE001 — 检索失败降级为空，不阻断问答
        log.warning("mem.recall_failed: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        content = str(r.get("content") or "")
        if content:
            out.append({"memory": content, "score": float(r.get("score") or 0.0)})
    return out


async def forget(memory_id: int | str) -> bool:
    """主动遗忘一条记忆。"""
    from . import db

    try:
        await db.delete_memory(int(memory_id))
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("mem.forget_failed: %s", e)
        return False


async def _legacy_recall(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """历史名称，等价于 recall（保留给既有调用点与测试）。"""
    return await recall(query, limit=limit)


__all__ = ["forget", "recall", "remember"]
