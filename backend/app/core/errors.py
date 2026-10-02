"""跨能力的可读错误：未配置供应商 / Key。

产品里没有假数据兜底（不返回「看起来像真结果的占位内容」）：云端能力没配置时，
工厂当场抛 `ProviderNotConfigured`，由 FastAPI 全局处理器转成
`503 {"code": "provider_not_configured", "message": …}`——message 是面向教师的一句话，
指到设置页。测试用 `tests/support/fakes.py` 的替身保证离线与确定性。
"""


class ProviderNotConfigured(RuntimeError):
    """云端能力未配置：不是故障，是引导教师去「设置」页配置供应商与 Key。"""
