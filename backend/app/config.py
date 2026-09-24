"""应用配置：pydantic-settings 读取环境变量 / .env。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "EduMind"
    debug: bool = True
    database_url: str = "sqlite:///./edumind.db"
    upload_dir: str = "data/uploads"
    vectors_db_path: str = "data/vectors.db"

    # ---- 对话 / 多模态：OpenAI 兼容方言（M2 阶段留空走 stub）----
    # stub / dashscope / deepseek / siliconflow；后三者为同一份实现的三种方言预设
    llm_provider: str = "stub"
    # 方言预设的覆盖项：填了即为准（换服务商只改这几项配置，不动代码）
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_vision_model: str = ""

    # ---- 向量化：独立于对话 provider ----
    # 留空 = 跟随对话方言（保持既有 .env 行为）；stub / hash / openai / dashscope / siliconflow
    embedding_provider: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_api_key: str = ""
    embedding_dimensions: int = 0  # >0 时随请求发送（dashscope text-embedding-v3 支持）

    # ---- 云端服务 Key ----
    dashscope_api_key: str = ""
    deepseek_api_key: str = ""
    siliconflow_api_key: str = ""
    mineru_token: str = ""
    bocha_api_key: str = ""

    # 录音转写：stub（默认，无 key 可跑）/ paraformer（阿里百炼，复用 DASHSCOPE_API_KEY）
    asr_provider: str = "stub"
    # 网络搜索：留空 = 有 BOCHA_API_KEY 走 bocha，否则 stub（无 key 底线）；可显式 stub / bocha
    search_provider: str = ""
    # PDF 解析策略：mineru / pypdf / mineru_then_pypdf（默认 = mineru 失败退 pypdf）
    pdf_strategy: str = "mineru_then_pypdf"

    # ---- RAG 策略（ADR-0003）：分块与检索都是按配置名选择的策略 ----
    # 分块策略：paragraph（默认，按段落/标题边界合并 + 相邻重叠）
    chunk_strategy: str = "paragraph"
    # 检索策略：vector_graph（默认，向量 + 图谱邻接融合）/ vector（纯向量）
    retrieval_strategy: str = "vector_graph"

    # ---- 冲突检测（ADR-0006）：近名预筛的余弦距离阈值，阈值内候选交 LLM 比对 ----
    conflict_distance_threshold: float = 0.3


settings = Settings()
