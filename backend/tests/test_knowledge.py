"""知识库：切片、BM25 检索、上下文拼装。

这是「文档入库后问答可引用」的核心逻辑；不测 UI，只测可复现的纯函数行为。
"""

from __future__ import annotations

from app import knowledge


def test_empty_text_yields_no_chunks() -> None:
    assert knowledge.chunk_text("") == []
    assert knowledge.chunk_text("   \n\n  ") == []


def test_short_text_is_single_chunk() -> None:
    text = "这是一段很短的说明。"
    assert knowledge.chunk_text(text) == [text]


def test_paragraphs_are_preserved() -> None:
    text = "第一段内容。\n\n第二段内容。"
    chunks = knowledge.chunk_text(text)
    assert len(chunks) == 1
    assert "第一段内容" in chunks[0] and "第二段内容" in chunks[0]


def test_long_paragraph_is_split_with_overlap() -> None:
    text = "甲" * 1000
    chunks = knowledge.chunk_text(text, size=400, overlap=80)
    assert len(chunks) >= 3
    assert all(len(c) <= 400 for c in chunks)
    # 相邻片段有重叠，避免把一句话切死
    assert chunks[0][-80:] == chunks[1][:80]


def test_rank_prefers_matching_chunk() -> None:
    chunks = [
        {"filename": "保单.txt", "content": "重疾险保额 50 万，等待期 90 天。"},
        {"filename": "菜单.txt", "content": "宫保鸡丁 38 元，米饭 2 元。"},
    ]
    hits = knowledge.rank_chunks("重疾险 等待期", chunks, top_k=2)
    assert hits, "应至少命中一条"
    assert hits[0]["filename"] == "保单.txt"
    assert hits[0]["score"] > 0


def test_rank_returns_empty_for_blank_query() -> None:
    assert knowledge.rank_chunks("", [{"content": "x"}]) == []


def test_rank_drops_zero_scores() -> None:
    hits = knowledge.rank_chunks("完全无关的词组", [{"content": "重疾险 保额"}], top_k=3)
    assert hits == []


def test_build_context_includes_filename() -> None:
    ctx = knowledge.build_context([{"filename": "a.txt", "content": "内容"}])
    assert "【a.txt】" in ctx and "内容" in ctx


def test_build_context_respects_budget() -> None:
    hits = [{"filename": "f", "content": "字" * 500} for _ in range(10)]
    ctx = knowledge.build_context(hits, max_chars=600)
    assert len(ctx) <= 700  # 允许结尾省略号
