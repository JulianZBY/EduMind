"""知识点标题向量的空间身份与待审保存信息；不包含供应商密钥。"""

import hashlib
import json
import math
from urllib.parse import urlsplit

from app.core.embedding.base import Embedder

TITLE_VECTOR_KEY = "_title_vector"


def title_vector_space(embedder: Embedder, dimension: int) -> str:
    """实现、非秘密服务身份、模型、请求／实际维度的稳定指纹（ADR-0008）。"""
    url = urlsplit(getattr(embedder, "base_url", ""))
    endpoint = f"{url.scheme}://{url.hostname or ''}:{url.port or ''}{url.path.rstrip('/')}"
    identity = {
        "implementation": f"{type(embedder).__module__}.{type(embedder).__qualname__}",
        "provider": embedder.name,
        "endpoint": endpoint,
        "model": getattr(embedder, "model", ""),
        "requested_dimension": getattr(embedder, "dimensions", getattr(embedder, "dim", 0)),
        "actual_dimension": dimension,
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def title_vector_record(title: str, values: list[float], embedder: Embedder) -> dict:
    return {"title": title, "values": values, "space": title_vector_space(embedder, len(values))}


def saved_title_vector(data: dict, title: str, embedder: Embedder) -> dict | None:
    """标题或能力空间变更／旧信息缺失时不复用，不在读取路径重新调用向量化。"""
    record = data.get(TITLE_VECTOR_KEY)
    if not isinstance(record, dict) or record.get("title") != title:
        return None
    values = record.get("values")
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values)
    ):
        return None
    if record.get("space") != title_vector_space(embedder, len(values)):
        return None
    return record
