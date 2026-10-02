"""OpenAI 兼容方言预设：千问 / DeepSeek / Kimi / GLM / MiniMax / 豆包 / 硅基流动只差
base_url + 模型名 + Key。

换云端能力只改配置——`LLM_PROVIDER` 选方言，`LLM_BASE_URL` / `LLM_MODEL` /
`LLM_API_KEY` / `LLM_VISION_MODEL` 可整体覆盖预设（换到未收录的服务商也只改配置）。
对话与向量化共用此表，保证「同一份 Key 与地址口径」。
模型清单原样拉取：供应商的 `/v1/models` 返回什么就展示什么（市场型平台如豆包 /
硅基流动会列出平台上架的全部模型，含第三方托管模型——都是该平台可调用的；
千问走官方 MaaS 平台 `maas.qianwenaiapi.com`，不再走阿里云百炼）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    """一家 OpenAI 兼容服务商的口径。空字段表示该方言不提供该能力。"""

    name: str
    base_url: str
    chat_model: str
    api_key_field: str = ""  # Settings 上存放该方言 Key 的字段名（空 = 该家不是内置方言）
    api_key_env: str = ""  # Key 从哪个环境变量读；内置方言用 api_key_field，配置声明的家用它
    vision_model: str = ""  # 空 = 无多模态（vision 抛 NotImplementedError）
    embed_model: str = ""  # 空 = 不提供 embedding（向量化另配 EMBEDDING_*）
    embed_dimensions: int = 0  # >0 = embedding 请求携带 dimensions（千问支持）
    extra_chat_models: tuple[str, ...] = ()  # 目录里补充的对话模型（配置声明的家用来列清单）
    extra_vision_models: tuple[str, ...] = ()  # 同上，多模态档
    extra_embed_models: tuple[str, ...] = ()  # 配置声明的全部向量化模型
    accepts_any_model: bool | None = None  # None 沿用内置策略；显式声明优先
    configured: bool = False  # 显式配置覆盖时不拼回内置补充模型
    label: str = ""  # 面向教师的名称（空 = 用目录预设；配置声明的家自带）
    note: str = ""  # 设置页里的一句话说明（空 = 用目录预设）
DIALECTS: dict[str, Dialect] = {
    # 千问（Qwen MaaS，官方统一 API 平台）：对话 + 多模态 + text-embedding-v3（1024/768/512 维）
    "qwen": Dialect(
        name="qwen",
        base_url="https://maas.qianwenaiapi.com/compatible-mode/v1",
        chat_model="qwen-plus",
        api_key_field="qwen_api_key",
        vision_model="qwen-vl-max",
        embed_model="text-embedding-v3",
        embed_dimensions=1024,
    ),
    # DeepSeek：对话 + 多模态（deepseek-flash / deepseek-v4-pro 均支持视觉）；官方不提供 /embeddings
    "deepseek": Dialect(
        name="deepseek",
        base_url="https://api.deepseek.com",
        chat_model="deepseek-flash",
        api_key_field="deepseek_api_key",
        vision_model="deepseek-v4-pro",
    ),
    # Kimi（Moonshot）：仅对话；多模态与向量化不在此目录内
    "moonshot": Dialect(
        name="moonshot",
        base_url="https://api.moonshot.cn/v1",
        chat_model="kimi-latest",
        api_key_field="moonshot_api_key",
    ),
    # 智谱 GLM：对话 + 多模态（glm-4.5v）+ embedding-3
    "zhipu": Dialect(
        name="zhipu",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        chat_model="glm-4.5",
        api_key_field="zhipu_api_key",
        vision_model="glm-4.5v",
        embed_model="embedding-3",
    ),
    # MiniMax：对话为主；多模态与向量化不在此目录内
    "minimax": Dialect(
        name="minimax",
        base_url="https://api.minimax.chat/v1",
        chat_model="MiniMax-Text-01",
        api_key_field="minimax_api_key",
    ),
    # 豆包（字节火山方舟）：模型 ID 也接受 ep- 接入点（目录外 ID 放行）
    "ark": Dialect(
        name="ark",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        chat_model="doubao-seed-1-6-250615",
        api_key_field="ark_api_key",
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
