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
    except Exception as e:  # pragma: no cover
        log.warning("mem.init_failed: " + str(e))
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


def recall(query: str, user_id: str = "default", limit: int = 5) -> list[dict]:
    """按 query 检索相关记忆。返回 [{memory, score, ...}]。"""
    _init()
    if not query or _client is None:
        return []
    try:
        res = _client.search(query, user_id=user_id, limit=limit)
        # mem0 返回格式可能是 list[dict] 或带 results 字段，统一成 list
        if isinstance(res, dict) and "results" in res:
            res = res["results"]
        return list(res or [])[:limit]
    except Exception as e:  # pragma: no cover
        log.warning("mem.search_failed: %s", e)
        return []


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
