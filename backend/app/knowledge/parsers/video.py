"""视频解析：OpenCV 关键帧抽帧 + qwen-vl 摘要。"""

import tempfile

import cv2

from app.core.llm.factory import get_llm
from app.knowledge.parsers.base import Parser

_FRAME_PROMPT = "这是教学视频的一帧，请概括画面内容与可能的知识点。"


class VideoParser(Parser):
    async def parse(self, file_path: str) -> str:
        llm = get_llm()
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频: {file_path}")
        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
            n = min(4, max(1, total))
            indices = [int(total * i / (n + 1)) for i in range(1, n + 1)] if total > 1 else [0]
            summaries = []
            with tempfile.TemporaryDirectory() as tmp:
                for idx in indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ok, frame = cap.read()
                    if not ok:
                        continue
                    frame_path = f"{tmp}/frame_{idx}.jpg"
                    cv2.imwrite(frame_path, frame)
                    s = await llm.vision(frame_path, _FRAME_PROMPT)
                    summaries.append(f"[帧 {idx}] {s}")
            return "\n".join(summaries)
        finally:
            cap.release()
