"""跨能力的可读错误：未配置供应商 / Key。

产品里没有假数据兜底（不返回「看起来像真结果的占位内容」）：云端能力没配置时，
工厂当场抛 `ProviderNotConfigured`，由 FastAPI 全局处理器转成
`503 {"code": "provider_not_configured", "message": …}`——message 是面向教师的一句话，
指到设置页。测试用 `tests/support/fakes.py` 的替身保证离线与确定性。
"""


class ProviderNotConfigured(RuntimeError):
    """云端能力未配置：不是故障，是引导教师去「设置」页配置供应商与 Key。"""


class GenerationFailed(RuntimeError):
    """本轮备课生成失败：课件 / 教案 / 提纲任一路没生成出来。

    与 `ProviderNotConfigured` 的区别：后者是「没配置」（引导去设置页），这里
    是「配好了但生成没成功」（可重试）。产品不用空课件 / 空教案冒充成功——
    由 FastAPI 全局处理器转成 `502 {"code": "generation_failed", "message": …}`。
    """
