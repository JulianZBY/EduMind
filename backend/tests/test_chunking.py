"""分段 chunking 测试。"""

from itertools import pairwise

from app.knowledge.chunking import chunk_text


def test_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_small_text_single_chunk():
    assert chunk_text("段落一内容") == ["段落一内容"]


def test_overlap_between_chunks():
    text = "\n\n".join(f"第{i}段：这是一段用于测试分段逻辑的教学内容文字" for i in range(30))
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    # 相邻 chunk 有重叠：前一个 chunk 尾部 = 后一个 chunk 头部（overlap 字符）
    for a, b in pairwise(chunks):
        assert a[-20:] == b[:20]


def test_long_paragraph_hard_split():
    text = "字" * 1500
    chunks = chunk_text(text, chunk_size=500, overlap=0)
    assert len(chunks) == 3
    assert all(len(c) == 500 for c in chunks)
