"""模型接入层单测：配置解析、流式/非流式调用、SDK 重试与模板兜底。

不触网：用 httpx.MockTransport 假冒 OpenAI 兼容端点。
"""

from __future__ import annotations

import json

import httpx
import pytest
from app import llm

SSE_HEAD = {"content-type": "text/event-stream"}


def _sse(*deltas: str) -> bytes:
    body = "".join(
        f"data: {json.dumps({'choices': [{'delta': {'content': d}}]})}\n\n" for d in deltas
    )
    body += "data: [DONE]\n\n"
    return body.encode()


def _inject(monkeypatch, handler) -> None:
    """注入 mock：拦截 litellm.acompletion 走 MockTransport，返回 litellm 兼容形态的响应。

    区分 stream=True（返回异步 chunk 迭代器）和 stream=False（返回含 choices 的响应对象）。
    错误 ≥400 → 抛 RuntimeError（模拟 litellm 失败），并按 num_retries 重试。
    """
    from types import SimpleNamespace

    import litellm

    async def _do_request(**kwargs):
        """执行一次 HTTP 请求 + 解析（返回 response 或 raise RuntimeError）。"""
        import httpx as _httpx
        http_client = _httpx.AsyncClient(transport=_httpx.MockTransport(handler))
        api_base = kwargs.get("api_base") or "http://mock.invalid/v1"
        send_kwargs = {k: v for k, v in kwargs.items() if k not in ("api_base", "api_key", "num_retries", "client", "stream_timeout", "timeout", "messages")}
        req = http_client.build_request(
            "POST",
            f"{api_base}chat/completions",
            json=send_kwargs,
            headers={"Authorization": f"Bearer {kwargs.get('api_key', '')}"},
        )
        resp = await http_client.send(req)
        await http_client.aclose()
        if resp.status_code >= 400:
            raise RuntimeError(f"mock {resp.status_code}: {resp.content[:200]!r}")
        return resp, kwargs

    async def _mock_acompletion(**kwargs):
        """带重试的 acompletion：≥5xx 时按 num_retries 重试，最后一次失败才抛出。"""
        num_retries = kwargs.get("num_retries", 1)
        stream = kwargs.get("stream", False)
        resp = None
        last_exc: Exception | None = None

        for attempt in range(num_retries + 1):
            try:
                resp, _ = await _do_request(**kwargs)
                last_exc = None
                break  # 成功 → 跳出
            except RuntimeError as e:
                last_exc = e
                if attempt >= num_retries:
                    raise  # 最后一次还失败 → 抛出（外层 create 捕获 → 模板兜底）
                # 还有重试次数 → 继续下一轮（handler 计数器会 +1）
                continue

        assert resp is not None and last_exc is None, "mock internal error"

        if stream:
            # 流式：解析 SSE bytes → 异步 chunk 迭代器
            raw = resp.content.decode("utf-8", errors="replace")
            chunks: list[SimpleNamespace] = []

            for line in raw.split("\n"):
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):].strip()
                if payload == "[DONE]":
                    continue
                try:
                    item = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                for choice in item.get("choices", []):
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    chunks.append(
                        SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    delta=SimpleNamespace(content=content),
                                    index=0,
                                    finish_reason=choice.get("finish_reason"),
                                ),
                            ],
                        ),
                    )

            async def _gen():
                for chunk in chunks:
                    yield chunk
            return _gen()

        # 非流式：解析 JSON → 响应对象
        data = json.loads(resp.content)

        def _build_msg(msg: dict) -> SimpleNamespace:
            tool_calls = None
            if msg.get("tool_calls"):
                tool_calls = [
                    SimpleNamespace(
                        id=tc.get("id", f"call_{i}"),
                        type="function",
                        function=SimpleNamespace(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        ),
                    )
                    for i, tc in enumerate(msg["tool_calls"])
                ]
            return SimpleNamespace(
                content=msg.get("content"),
                tool_calls=tool_calls,
                role=msg.get("role", "assistant"),
            )

        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=_build_msg(c["message"]), finish_reason=c.get("finish_reason"))
                for c in data["choices"]
            ],
            model=data.get("model", kwargs.get("model", "")),
        )

    monkeypatch.setattr(litellm, "acompletion", _mock_acompletion)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    llm.invalidate()
    monkeypatch.setattr(llm, "_client_singleton", None)
    yield
    llm.invalidate()


async def test_no_config_yields_template() -> None:
    """未配置模型 → 只产出一段模板，且来源标 template。"""
    llm._cfg = {}
    out = [x async for x in llm.stream_narrate("sys", "user", "模板答案")]
    assert out == [("模板答案", "template")]


async def test_stream_reads_sse_deltas(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk-test"
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, headers=SSE_HEAD, content=_sse("你", "好"))

    _inject(monkeypatch, handler)
    llm._cfg = {"base": "http://mock.invalid/v1", "key": "sk-test", "model": "gpt-4o-mini", "provider": "openai", "litellm_model": "openai/gpt-4o-mini"}
    out = [x async for x in llm.stream_narrate("sys", "user", "模板")]
    assert out == [("你", "llm"), ("好", "llm")]


async def test_stream_retries_then_succeeds(monkeypatch) -> None:
    """第一次 500 → SDK 自动重试 → 拿到增量，而不是整体降级成模板。"""
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return httpx.Response(200, headers=SSE_HEAD, content=_sse("成功"))

    _inject(monkeypatch, handler)
    llm._cfg = {"base": "http://mock.invalid/v1", "key": "sk-test", "model": "gpt-4o-mini", "provider": "openai", "litellm_model": "openai/gpt-4o-mini"}
    out = [x async for x in llm.stream_narrate("sys", "user", "模板")]
    assert calls["n"] == 2, "SDK 应自动重试一次"
    assert out == [("成功", "llm")]


async def test_stream_all_fail_yields_template(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    _inject(monkeypatch, handler)
    llm._cfg = {"base": "http://mock.invalid/v1", "key": "sk-test", "model": "gpt-4o-mini", "provider": "openai", "litellm_model": "openai/gpt-4o-mini"}
    out = [x async for x in llm.stream_narrate("sys", "user", "模板答案")]
    assert out == [("模板答案", "template")]


async def test_json_complete_parses_object(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is False
        return httpx.Response(200, json={"choices": [{"message": {"content": '前缀 {"a": 1} 后缀'}}]})

    _inject(monkeypatch, handler)
    llm._cfg = {"base": "http://mock.invalid/v1", "key": "sk-test", "model": "gpt-4o-mini", "provider": "openai", "litellm_model": "openai/gpt-4o-mini"}
    assert await llm.json_complete("sys", "user") == {"a": 1}


async def test_json_complete_invalid_json_returns_none(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    _inject(monkeypatch, handler)
    llm._cfg = {"base": "http://mock.invalid/v1", "key": "sk-test", "model": "gpt-4o-mini", "provider": "openai", "litellm_model": "openai/gpt-4o-mini"}
    assert await llm.json_complete("sys", "user") is None


# ---------------------------------------------------------------------------
# 灵活化：base_url / model 可留空（走 OpenAI 默认端点与默认模型），仅 api_key 必填
# ---------------------------------------------------------------------------


async def test_empty_base_uses_default_endpoint() -> None:
    """base 留空 → _CompatClient 内 cfg['base'] 为空，走 LiteLLM 默认端点路由。"""
    client = llm._sdk({"base": "", "key": "sk-x", "model": "gpt-4o-mini", "litellm_model": "openai/gpt-4o-mini", "provider": "openai"}, timeout=10.0)
    # _CompatClient 是 LiteLLM 兼容层，不再直接暴露 base_url；验证 cfg 正确传入即可
    assert client._cfg["base"] == ""


async def test_empty_model_falls_back_to_default(monkeypatch) -> None:
    """model 留空 → 调用时兜底 gpt-4o-mini（OpenAI 兼容端点普遍接受）。"""

    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, headers=SSE_HEAD, content=_sse("ok"))

    _inject(monkeypatch, handler)
    llm._cfg = {"base": "http://mock.invalid/v1", "key": "sk-test", "model": "", "provider": "openai", "litellm_model": "openai/gpt-4o-mini"}
    out = [x async for x in llm.stream_narrate("sys", "user", "模板")]
    assert out == [("ok", "llm")]
    assert captured["model"] == "openai/gpt-4o-mini"


async def test_long_api_key_accepted(temp_db, monkeypatch) -> None:
    """长 key（>500 字，旧上限）可存：AI_KEY_MAX_LEN=2000 不报错。"""
    from app import main, vault
    # vault 已通过 conftest VAULT_PASSPHRASE 初始化；若未激活则兜底初始化
    if not vault.is_active():
        vault.init_master_passphrase("test-passphrase-for-unit-tests-12345")
        vault.activate()

    long_key = "k" * 1500
    r = await main.put_settings({"settings": {"ai_api_key": long_key, "ai_enabled": "on", "ai_base_url": "", "ai_model": ""}})
    assert not r["errors"], r["errors"]
    # vault 激活后 ai_api_key 被加密存储，解密后应等于原始 key
    from app.vault import decrypt_secret
    assert await decrypt_secret(r["applied"]["ai_api_key"]) == long_key
    assert r["applied"]["ai_base_url"] == ""
    assert r["applied"]["ai_model"] == ""


async def test_api_key_over_2000_rejected(temp_db, monkeypatch) -> None:
    """超长 key（>2000）拒绝，避免误存异常数据。"""
    from app import main, vault
    if not vault.is_active():
        vault.init_master_passphrase("test-passphrase-for-unit-tests-12345")
        vault.activate()

    r = await main.put_settings({"settings": {"ai_api_key": "k" * 2001}})
    assert any("过长" in e for e in r["errors"])
    assert "ai_api_key" not in r["applied"]


async def test_base_url_requires_http_prefix_when_set(temp_db) -> None:
    """填了 base_url 但没 http 前缀 → 报错；留空 → 通过。"""
    from app import main

    r1 = await main.put_settings({"settings": {"ai_base_url": "not-a-url"}})
    assert any("http" in e for e in r1["errors"])
    r2 = await main.put_settings({"settings": {"ai_base_url": ""}})
    assert not r2["errors"]
    assert r2["applied"]["ai_base_url"] == ""
