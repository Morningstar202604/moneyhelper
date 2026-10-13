"""可观测性层 —— 接 Langfuse（自托管，MIT core）。

设计原则：
- **没配 LANGFUSE_* 环境变量就完全 no-op**：所有函数变成空壳，零开销；
- 配了就自动 trace 每次 LLM 调用和工具调用，trace 树/token 成本/延迟/用户反馈全有；
- 替换原来自写的 audit_logger middleware + audit_logs 表（v2.0 迁移，见 docs/ARCHITECTURE-v2.md）。

用法：
    from .observability import trace_llm, trace_tool, flush

    async def my_llm_call(...):
        with trace_llm("chat", model=..., messages=...) as span:
            out = ...
            span.output = out
            return out
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from .logging_utils import get_logger

log = get_logger(__name__)

_lf: Any = None
_enabled = False


def _init() -> None:
    """懒初始化：读 env，配了才建 client。失败不炸，降级 no-op。"""
    global _lf, _enabled
    if _lf is not None or _enabled:
        return
    host = os.getenv("LANGFUSE_HOST", "").strip()
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    if not (host and pk and sk):
        return  # 没配，no-op
    try:
        from langfuse import Langfuse  # type: ignore

        _lf = Langfuse(host=host, public_key=pk, secret_key=sk)
        _enabled = True
        log.info("langfuse.connected", host=host)
    except Exception as e:  # pragma: no cover - 降级路径
        log.warning("langfuse.init_failed", error=str(e))
        _lf = None
        _enabled = False


@contextmanager
def trace_llm(name: str, model: str = "", messages: list | None = None, **meta: Any):
    """包一次 LLM 调用。没接 Langfuse 就直通。"""
    _init()
    if not _enabled or _lf is None:
        yield None
        return
    span = _lf.trace(name=name, metadata={"model": model, **meta})
    try:
        yield span
    except Exception:
        span.generation(end_time=None, level="ERROR")
        raise


@contextmanager
def trace_tool(name: str, args: dict | None = None, **meta: Any):
    """包一次工具调用。"""
    _init()
    if not _enabled or _lf is None:
        yield None
        return
    span = _lf.span(name=f"tool.{name}", metadata={"args": args or {}, **meta})
    try:
        yield span
    except Exception:
        span.end(level="ERROR")
        raise


def flush() -> None:
    """优雅停机时调用：把缓存的 trace 刷出去。"""
    _init()
    if _enabled and _lf is not None:
        try:
            _lf.flush()
        except Exception:  # pragma: no cover
            pass
