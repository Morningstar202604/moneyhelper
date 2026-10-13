"""可观测性层 —— 接 Arize Phoenix（开源，单容器本地跑，不需要外部账号）。

设计原则：
- **没配 PHOENIX_ENDPOINT 环境变量就完全 no-op**：所有函数变成空壳，零开销；
- 配了就自动 trace 每次 LLM 调用和工具调用，trace 树/token 成本/延迟全有；
- 基于 OpenTelemetry 标准格式，Phoenix / Jaeger / Zipkin 都能接；
- 替换原来自写的 audit_logger middleware + audit_logs 表（v2.0 迁移）。

用法：
    from .observability import trace_llm, trace_tool, flush

    async def my_llm_call(...):
        with trace_llm("chat", model=..., messages=...) as span:
            out = ...
            span.output = out
            return out

启动 Phoenix：
    uvx arize-phoenix serve
    # 然后设 PHOENIX_ENDPOINT=http://localhost:6006/v1/traces
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from .logging_utils import get_logger

log = get_logger(__name__)

_tracer: Any = None
_enabled = False


def _init() -> None:
    """懒初始化：读 env，配了才建 tracer。失败不炸，降级 no-op。"""
    global _tracer, _enabled
    if _tracer is not None or _enabled:
        return
    endpoint = os.getenv("PHOENIX_ENDPOINT", "").strip()
    if not endpoint:
        return  # 没配，no-op
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": "xiaoman"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("xiaoman")
        _enabled = True
        log.info("phoenix.connected", endpoint=endpoint)
    except Exception as e:  # pragma: no cover - 降级路径
        log.warning("phoenix.init_failed: " + str(e))
        _tracer = None
        _enabled = False


class _NoOpSpan:
    """no-op 占位 span，保持接口一致。"""
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def set_attribute(self, k: str, v: Any): pass
    def set_status(self, *a): pass


@contextmanager
def trace_llm(name: str, model: str = "", messages: list | None = None, **meta: Any):
    """包一次 LLM 调用。没接 Phoenix 就直通。"""
    _init()
    if not _enabled or _tracer is None:
        yield _NoOpSpan()
        return
    span = _tracer.start_as_current_span(f"llm.{name}")
    try:
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.messages_count", len(messages) if messages else 0)
        for k, v in meta.items():
            span.set_attribute(f"llm.{k}", str(v))
        yield span
    except Exception:
        span.set_status(2)  # ERROR
        raise
    finally:
        span.end()


@contextmanager
def trace_tool(name: str, args: dict | None = None, **meta: Any):
    """包一次工具调用。"""
    _init()
    if not _enabled or _tracer is None:
        yield _NoOpSpan()
        return
    span = _tracer.start_as_current_span(f"tool.{name}")
    try:
        span.set_attribute("tool.args", str(args or {}))
        for k, v in meta.items():
            span.set_attribute(f"tool.{k}", str(v))
        yield span
    except Exception:
        span.set_status(2)  # ERROR
        raise
    finally:
        span.end()


def flush() -> None:
    """优雅停机时调用：把缓存的 trace 刷出去。"""
    _init()
    # BatchSpanProcessor 会自动刷，这里不用额外操作
