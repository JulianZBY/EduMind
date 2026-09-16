"""桩转写器：无 key 可跑，返回固定文字稿，供 stub 模式下录音管道联调与测试。"""

from app.core.asr.base import Transcriber

# 固定文字稿：stub 网关不命中知识提取提示词 → 图谱提取空结果，文档确定性「已完成」；
# 检索走长度向量，测试以空库种子断言命中本文本。
STUB_TRANSCRIPT = (
    "（stub 录音转写）本段录音讲解计算机网络概述：首先介绍 OSI 七层参考模型的分层思想，"
    "随后重点讲解 TCP 三次握手建立可靠连接的过程，最后说明滑动窗口机制如何实现流量控制。"
)


class StubTranscriber(Transcriber):
    name = "stub"

    async def transcribe(self, file_path: str) -> str:
        return STUB_TRANSCRIPT
