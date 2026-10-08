"""应用配置：pydantic-settings 读取环境变量 / .env。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 相对路径一律锚定 backend/ 目录（本文件在 backend/app/ 下），不再随启动目录漂移：
# 从仓库根还是 backend/ 启动，库、上传目录、生成物目录都落在同一处（M3）。
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "EduMind"
    debug: bool = True
    database_url: str = f"sqlite:///{(BASE_DIR / 'edumind.db').as_posix()}"
    upload_dir: str = str(BASE_DIR / "data" / "uploads")
    vectors_db_path: str = str(BASE_DIR / "data" / "vectors.db")
    # 生成物落盘目录的唯一事实源：generate/ 与 files 下载接口都从这里取（M3）
    output_dir: str = str(BASE_DIR / "data" / "output")
    # 单次上传大小上限（字节）：默认 200 MB，保护进程内存与磁盘（M4）
    max_upload_bytes: int = 200 * 1024 * 1024

    # ---- 对话 / 多模态：OpenAI 兼容方言（留空 = 未配置：产品不提供假数据兜底）----
    # qwen / deepseek / moonshot / zhipu / minimax / ark / siliconflow / custom
    llm_provider: str = ""
    # 方言预设的覆盖项：填了即为准（换服务商只改这几项配置，不动代码）
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_vision_model: str = ""

    # ---- 向量化：独立于对话 provider ----
    # 留空 = 跟随对话方言（保持既有 .env 行为）；hash / openai / qwen / siliconflow
    embedding_provider: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_api_key: str = ""
    embedding_dimensions: int = 0  # >0 时随请求发送（千问 text-embedding-v3 支持）

    # ---- 云端服务 Key ----
    qwen_api_key: str = ""
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    zhipu_api_key: str = ""
    minimax_api_key: str = ""
    ark_api_key: str = ""
    siliconflow_api_key: str = ""
    mineru_token: str = ""
    bocha_api_key: str = ""
    # 录音转写：留空 = 自动（有百炼 Key 走 paraformer，否则提示未配置；无假转写兜底）
    asr_provider: str = ""
    # 百炼语音转写 Key：paraformer 是阿里云百炼的服务，与千问 MaaS 的 Key 不通用
    asr_api_key: str = ""
    # 网络搜索：留空 = 有 BOCHA_API_KEY 走 bocha，否则提示未配置；可显式 bocha
    search_provider: str = ""
    # PDF 解析策略：mineru / pypdf / mineru_then_pypdf（默认 = mineru 失败退 pypdf）
    pdf_strategy: str = "mineru_then_pypdf"

    # ---- RAG 策略（ADR-0003）：分块与检索都是按配置名选择的策略 ----
    # 分块策略：paragraph（默认，按段落/标题边界合并 + 相邻重叠）
    chunk_strategy: str = "paragraph"
    # 检索策略：vector_graph（默认，向量 + 图谱邻接融合）/ vector（纯向量）
    retrieval_strategy: str = "vector_graph"
    # 检索命中阈值（票 01，ADR-0007）：命中与查询的余弦距离超过它的直接丢弃（不是降权），
    # 默认保守取宽避免误杀真实内容。与冲突检测的 conflict_distance_threshold
    # 是两条独立水位（那是标题近名预筛的），不共用。
    retrieval_distance_threshold: float = 0.8

    # ---- 任务级模型（CONTEXT.md「任务级模型」）----
    # 按任务分别选「供应商实例 + 模型档位」：留空 = 回落全局默认。
    # task_provider_* 是供应商实例 id（设置页「添加供应商」产生）；task_model_* 是该实例方言目录里的模型。
    task_provider_intent: str = ""
    task_provider_generate: str = ""
    task_provider_conflict: str = ""
    task_model_intent: str = ""
    task_model_generate: str = ""
    task_model_conflict: str = ""

    # ---- 供应商实例（多供应商并存）----
    # 默认供应商实例 id：设置页「添加供应商」产生；留空 = 走 legacy 单供应商路径（llm_provider + 各家 Key）。
    default_provider_instance: str = ""

    # ---- 冲突检测（ADR-0006）：近名预筛的余弦距离阈值，阈值内候选交 LLM 比对 ----
    conflict_distance_threshold: float = 0.3


settings = Settings()
