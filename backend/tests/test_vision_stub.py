"""视觉提取 stub 的测试：能力缝（stub 实现）与 HTTP 缝（图片/视频走到终态）。

票 15 的两条底线：
- ADR-0003「每项能力 = 接口 + 工厂 + 必有 stub」——对话接口的视觉方法在 stub 模式下不再抛
  `NotImplementedError`，返回**确定性**且带「stub 视觉提取」标记的占位解读；
- `docs/api/stub-mode.md`「无 Key 全链路可跑」——无任何云端 Key 时上传图片/视频能走到
  终态「已完成」（状态口径见 CONTEXT.md 第 4 节：处理中 → 已完成 / 有冲突 / 失败）。

全程跑在 stub 模式（conftest 隔离临时库与临时落盘目录），不依赖任何真实 Key 或网络。
"""

from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.core.llm.base import LLMProvider
from app.core.llm.factory import get_llm
from app.core.llm.providers.stub import StubProvider
from app.db import init_db
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在

# stub 视觉提取的标记（CONTEXT.md 措辞纪律：说「stub 视觉提取」）。教师看到的分块内容里
# 必须带这个标记，才不会被误当成真实识别结果。
_STUB_VISION_MARK = "[stub 视觉提取]"

_IMAGE_PROMPT = "请描述这张图片的内容，包括文字、图表、公式等，用于教学知识提取。"


def _upload(filename: str, content: bytes) -> dict:
    """上传一份资料，返回上传响应体（断言上传本身成功）。"""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _detail(doc_id: str) -> dict:
    response = client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _png_bytes() -> bytes:
    """一张真实的极小 PNG（按真实字节上传，而不是随便造的假文件）。"""
    ok, buf = cv2.imencode(".png", np.zeros((16, 16, 3), dtype=np.uint8))
    assert ok
    return buf.tobytes()


def _avi_bytes(tmp_path: Path) -> bytes:
    """一段真实的极短 AVI（MJPG）：视频解析路径要走 OpenCV 抽帧，假字节进不去。"""
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc("M", "J", "P", "G"), 5.0, (64, 48))
    assert writer.isOpened(), "本机 OpenCV 无法写 MJPG/AVI"
    for i in range(8):
        writer.write(np.full((48, 64, 3), i * 20, dtype=np.uint8))
    writer.release()
    return path.read_bytes()


# ---- 能力缝：stub 必须实现视觉提取，且结果是确定性的、带标记的 ----


async def test_stub_provider_vision_returns_marked_deterministic_text():
    """同一个输入两次调用返回同一段文本，且首行就写明这是 stub 视觉提取。"""
    provider = StubProvider()

    first = await provider.vision("blackboard.png", _IMAGE_PROMPT)
    second = await provider.vision("blackboard.png", _IMAGE_PROMPT)

    assert first.startswith(_STUB_VISION_MARK)
    assert first == second  # 确定性：不依赖随机数、时间、网络
    assert "不是真实识别" in first  # 标记之外还要说清性质，防止教师误读


async def test_vision_is_reachable_through_the_selected_provider_in_stub_mode():
    """工厂按配置选出的 provider 就能做视觉提取（ADR-0003 的「接口 + 工厂 + 必有 stub」）。"""
    provider: LLMProvider = get_llm()

    assert provider.name == "stub"  # 无任何云端 Key 时工厂选中的就是 stub
    assert _STUB_VISION_MARK in await provider.vision("blackboard.png", _IMAGE_PROMPT)


# ---- HTTP 缝：stub 模式下图片/视频上传走到终态「已完成」 ----


def test_image_upload_reaches_completed_in_stub_mode():
    """上传图片：状态从「处理中」走到终态「已完成」，分块可检索且标明是 stub 提取。"""
    created = _upload("blackboard.png", _png_bytes())

    assert created["status"] == "处理中"  # 立即返回，不等解析
    detail = _detail(created["id"])
    assert detail["status"] == "已完成"  # 无 Key 的 stub 模式下不再必然「失败」
    assert detail["parsed_at"]  # 终态才写完成时间
    assert detail["chunk_count"] == len(detail["chunks"]) >= 1
    assert any(_STUB_VISION_MARK in chunk["content"] for chunk in detail["chunks"])


def test_video_upload_reaches_completed_in_stub_mode(tmp_path):
    """上传视频：抽帧后逐帧走同一视觉能力，同样走到终态「已完成」。"""
    created = _upload("clip.avi", _avi_bytes(tmp_path))

    assert created["status"] == "处理中"
    detail = _detail(created["id"])
    assert detail["status"] == "已完成"
    assert detail["chunk_count"] == len(detail["chunks"]) >= 1
    content = "\n".join(chunk["content"] for chunk in detail["chunks"])
    assert "[帧 " in content  # 视频路径的形态：逐帧解读汇总
    assert _STUB_VISION_MARK in content
