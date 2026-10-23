"""知识库：把上传的文档切成片段，按 BM25 检索后注入回答。

与「长期记忆」的区别：
  - 长期记忆是用户主动记住的短句（偏好、家庭背景），条数少、句子短；
  - 知识库是用户上传的长文档（合同、保单、产品说明），必须切片才能命中。

为什么复用 BM25 而不上向量库：
  rank_bm25 已在依赖里（记忆检索在用），中文分词的领域规则也已验证；
  引入 embedding 需要外部 API 或本地模型（几百 MB），与"本地优先、零外网"冲突。
  接口按 retriever(query, docs) -> ranked 设计，将来换向量实现只需替换本函数。
"""

from __future__ import annotations

import re
from typing import Any

# 片段长度：中文按字符算。400 字约等于一段完整论述，再长会稀释关键词权重。
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
# 单次最多注入几段：太多会挤占上下文，也会让模型抓不住重点
DEFAULT_TOP_K = 4


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按段落优先切分，段落过长再按字符滑窗切。

    直接在字符上硬切会把一句话切断（BM25 仍然能命中，但注入给模型的片段读起来是断的）。
    先按空行/换行分段，短段落合并到 size 以内，再对超长段落做带重叠的滑窗。
    """
    raw = str(text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            step = max(1, size - overlap)
            for i in range(0, len(para), step):
                piece = para[i : i + size]
                if piece.strip():
                    chunks.append(piece.strip())
                if i + size >= len(para):
                    break
            continue
        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}" if buf else para
        else:
            if buf:
                chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


def _tokens(text: str) -> list[str]:
    """与 db/memory.py 一致的中文分词：双字 + 单字兜底，英文按词。"""
    low = str(text or "").lower()
    toks: list[str] = []
    for seg in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", low):
        if re.fullmatch(r"[\u4e00-\u9fff]+", seg):
            for i in range(len(seg) - 1):
                toks.append(seg[i : i + 2])
            toks.extend(seg)
        else:
            toks.append(seg)
    return toks


def rank_chunks(query: str, chunks: list[dict[str, Any]], top_k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """给片段打分排序。chunks 元素需含 `content`（可选 `filename`/`id`）。

    返回带 score 的片段（只保留命中项）。BM25L 对长文档更稳，
    与记忆检索保持同一实现，避免两套打分口径。
    """
    q = str(query or "").strip().lower()
    if not q or not chunks:
        return []
    from rank_bm25 import BM25L

    corpus = [_tokens(str(c.get("content") or "")) for c in chunks]
    if not any(corpus):
        return []
    bm25 = BM25L(corpus)
    scores = bm25.get_scores(_tokens(q))
    ranked = sorted(zip(chunks, scores, strict=False), key=lambda x: x[1], reverse=True)
    out: list[dict[str, Any]] = []
    for item, score in ranked[: max(1, top_k)]:
        if score <= 0:
            continue
        row = dict(item)
        row["score"] = round(float(score), 3)
        out.append(row)
    return out


def build_context(hits: list[dict[str, Any]], max_chars: int = 2400) -> str:
    """把命中的片段拼成注入文本；超出预算就按得分顺序截断。"""
    parts: list[str] = []
    used = 0
    for h in hits:
        name = str(h.get("filename") or "").strip()
        body = str(h.get("content") or "").strip()
        if not body:
            continue
        block = f"【{name}】\n{body}" if name else body
        if used + len(block) > max_chars:
            remain = max_chars - used
            if remain > 80:
                parts.append(block[:remain].rstrip() + "…")
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)
