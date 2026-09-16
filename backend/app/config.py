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

    # ---- 云端服务（M2 阶段留空走 stub）----
    llm_provider: str = "stub"  # stub / dashscope / deepseek
    # 录音转写：stub（默认，无 key 可跑）/ paraformer（阿里百炼，复用 DASHSCOPE_API_KEY）
    asr_provider: str = "stub"
    dashscope_api_key: str = ""
    deepseek_api_key: str = ""
    siliconflow_api_key: str = ""
    mineru_token: str = ""
    bocha_api_key: str = ""

    # ---- 冲突检测（ADR-0001）：近名预筛的余弦距离阈值，阈值内候选交 LLM 比对 ----
    conflict_distance_threshold: float = 0.3


settings = Settings()
