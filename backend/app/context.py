"""上下文工程 —— 用 tiktoken（OpenAI 官方）精确管理上下文窗口。

不重复造轮子：
- tiktoken 是 OpenAI 官方 token 计数器，精确到每个模型的 BPE 分词
- 超过窗口阈值时，自动压缩早期历史（保留 system + 最新 N 条）
- 比手写"按条数截断"精确得多

用法：
    from .context import trim_messages
    trimmed = trim_messages(messages, max_tokens=6000)
"""

from __future__ import annotations

import tiktoken

from .logging_utils import get_logger

log = get_logger(__name__)

# 缓存编码器（懒加载，避免启动时加载大模型）
_enc: tiktoken.Encoding | None = None


def _get_enc() -> tiktoken.Encoding:
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")  # GPT-4 / GPT-3.5-turbo 通用
    return _enc


def count_tokens(text: str) -> int:
    """精确计算一段文本的 token 数。"""
    if not text:
        return 0
    return len(_get_enc().encode(text))


def count_messages_tokens(messages: list[dict]) -> int:
    """计算一组 messages 的总 token 数（含 role 开销）。"""
    total = 0
    for m in messages:
        total += 4  # 每条 message 的 role/分隔符开销
        total += count_tokens(m.get("content", ""))
    return total


def trim_messages(
    messages: list[dict],
    max_tokens: int = 6000,
    reserve_recent: int = 4,
) -> list[dict]:
    """智能裁剪 messages：保留 system + 最新 N 条，中间的摘要化。

    - system message 永远保留
    - 最新 reserve_recent 条永远保留
    - 中间的旧消息如果超 token 预算，截断或丢弃
    """
    total = count_messages_tokens(messages)
    if total <= max_tokens:
        return messages

    log.info("context.trim before=%s max=%s", total, max_tokens)

    # 分离 system 和普通消息
    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]

    # 保留最新 N 条
    if len(other_msgs) <= reserve_recent:
        return messages

    kept = other_msgs[-reserve_recent:]
    old = other_msgs[:-reserve_recent]

    # 旧消息合并成一条摘要 system
    if old:
        old_summary = "【历史对话摘要】\n" + "\n".join(
            f"- {m.get('role','?')}: {str(m.get('content',''))[:100]}" for m in old
        )
        system_msgs.append({"role": "system", "content": old_summary[:1000]})

    result = system_msgs + kept
    after = count_messages_tokens(result)
    log.info("context.trim.done after=%s", after)
    return result
