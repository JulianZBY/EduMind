"""OpenAI 兼容方言预设：dashscope / deepseek / 硅基流动只差 base_url + 模型名 + Key。

换云端能力只改配置——`LLM_PROVIDER` 选方言，`LLM_BASE_URL` / `LLM_MODEL` /
`LLM_API_KEY` / `LLM_VISION_MODEL` 可整体覆盖预设（换到未收录的服务商也只改配置）。
对话与向量化共用此表，保证「同一份 Key 与地址口径」。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    """一家 OpenAI 兼容服务商的口径。空字段表示该方言不提供该能力。"""

    name: str
    base_url: str
    chat_model: str
    api_key_field: str  # Settings 上存放该方言 Key 的字段名
    vision_model: str = ""  # 空 = 无多模态（vision 抛 NotImplementedError）
    embed_model: str = ""  # 空 = 不提供 embedding（向量化另配 EMBEDDING_*）
    embed_dimensions: int = 0  # >0 = embedding 请求携带 dimensions（dashscope 支持）


DIALECTS: dict[str, Dialect] = {
    # 阿里云百炼兼容模式：对话 + 多模态 + text-embedding-v3（1024/768/512 维）
    "dashscope": Dialect(
        name="dashscope",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        chat_model="qwen-plus",
        api_key_field="dashscope_api_key",
        vision_model="qwen-vl-max",
        embed_model="text-embedding-v3",
        embed_dimensions=1024,
    ),
    # DeepSeek：仅对话（官方不加/embeddings 与 /vision），embedding 由 EMBEDDING_* 另配
    "deepseek": Dialect(
        name="deepseek",
        base_url="https://api.deepseek.com",
        chat_model="deepseek-chat",
        api_key_field="deepseek_api_key",
    ),
    # 硅基流动：对话 + 多模态 + 托管 bge-large-zh（1024 维）
    "siliconflow": Dialect(
        name="siliconflow",
        base_url="https://api.siliconflow.cn/v1",
        chat_model="Qwen/Qwen2.5-7B-Instruct",
        api_key_field="siliconflow_api_key",
        vision_model="Qwen/Qwen2.5-VL-72B-Instruct",
        embed_model="BAAI/bge-large-zh-v1.5",
    ),
}
