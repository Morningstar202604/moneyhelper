"""长记忆层 —— 接 mem0（2026 年 local-first 首选）。

替换原来手写的 memory 表 + reflections + BM25 检索（~300 行）。
mem0 自带：事实抽取、去重、更新、rerank、metadata filtering。

设计：
- 本地 chroma 向量库，数据落 ./data/mem0，零外部服务；
- mem0 初始化失败（没装依赖/没配 LLM）就降级成 no-op，不炸主流程；
- 旧 memory 表保留读兼容，新写入走这里，双写过渡期后删旧表。

用法：
    from .mem import remember, recall
    remember("用户下个月要交房租 5000")
    hits = recall("用户最近有什么固定支出")
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .logging_utils import get_logger

log = get_logger(__name__)

_client: Any = None
_ready = False


def _data_dir() -> Path:
    d = Path(__file__).resolve().parent.parent / "data" / "mem0"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _init() -> None:
    """懒初始化 mem0。失败降级 no-op。"""
    global _client, _ready
    if _ready:
        return
    _ready = True
    try:
        from mem0 import Memory  # type: ignore

        # local-first：chroma 本地持久化，不连外部向量服务
        cfg = {
            "vector_store": {
                "provider": "chroma",
                "config": {"path": str(_data_dir()), "collection_name": "xiaoman_mem"},
            },
            # llm 走 LiteLLM
            "llm": {
                "provider": "litellm",
                "config": {"model": os.getenv("LLM_MODEL", "deepseek/deepseek-chat")},
            },
            # embedder 用 OpenAI（mem0 支持的 provider）
            "embedder": {
                "provider": "openai",
                "config": {"model": os.getenv("EMBED_MODEL", "text-embedding-3-small")},
            },
        }
        _client = Memory.from_config(cfg)
        log.info("mem.ready path=%s", _data_dir())
    except Exception as e:  # noqa: BLE001 — 无 embedding 凭据是预期路径，PDF 降级检索
        # 常见原因：自建/国产端点没有 embedding 模型 → mem0 初始化失败。
        # 这是预期的优雅降级（recall 自动回退到 _legacy_recall 关键词检索），
        # 不是故障；用 INFO 记录并说明回退目标，避免被误读为启动报错。
        log.info("mem.degraded: %s — 长期记忆检索回退为关键词近似检索（功能可用）", e)
        _client = None


def remember(text: str, user_id: str = "default") -> bool:
    """存一条长期记忆。成功返回 True。"""
    _init()
    if not text or _client is None:
        return False
    try:
        _client.add(text, user_id=user_id)
        return True
    except Exception as e:  # pragma: no cover
        log.warning("mem.add_failed: %s", e)
        return False


async def recall(query: str, user_id: str = "default", limit: int = 5) -> list[dict]:
    """按 query 检索相关记忆。返回 [{memory, score, ...}]。

    mem0 可用时走向量检索；不可用（无 embedding 凭据等）自动降级为
    旧 user_memory 表（service._try_save_memory 写入）的关键词近似检索。
    """
    _init()
    if _client is not None:
        try:
            res = _client.search(query, user_id=user_id, limit=limit)
            # mem0 返回格式可能是 list[dict] 或带 results 字段，统一成 list
            if isinstance(res, dict) and "results" in res:
                res = res["results"]
            return list(res or [])[:limit]
        except Exception as e:  # pragma: no cover
            log.warning("mem.search_failed: %s", e)
    return await _legacy_recall(query, limit)


async def _legacy_recall(query: str, limit: int) -> list[dict]:
    """无向量环境的关键词近似检索：字符二元组重叠打分（个人记忆量级足够）。"""
    try:
        from . import db

        rows = await db.list_memory()
    except Exception as e:  # pragma: no cover
        log.warning("mem.legacy_recall_failed: %s", e)
        return []
    q = (query or "").strip()
    if not q:
        return [{"memory": str(r.get("content") or ""), "score": 0.0} for r in rows[:limit]]
    scored: list[dict] = []
    for r in rows:
        content = str(r.get("content") or "")
        score = _bigram_overlap(q, content)
        if score > 0:
            scored.append({"memory": content, "score": round(score, 3)})
    scored.sort(key=lambda x: -float(x["score"]))
    return scored[:limit]


def _bigram_overlap(a: str, b: str) -> float:
    """a 的字符二元组有多少比例出现在 b 中（0-1）。中文短句下的廉价近似检索。"""
    def grams(s: str) -> set[str]:
        s = re.sub(r"\s+", "", s)
        return {s[i : i + 2] for i in range(len(s) - 1)} or ({s} if s else set())

    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga)


def forget(memory_id: str, user_id: str = "default") -> bool:
    """主动遗忘一条记忆。"""
    _init()
    if _client is None:
        return False
    try:
        _client.delete(memory_id)
        return True
    except Exception:  # pragma: no cover
        return False
