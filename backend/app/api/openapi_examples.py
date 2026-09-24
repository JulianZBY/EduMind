"""OpenAPI 注解公用片段:响应示例与错误码文案的唯一出处。

接口纪律要求每个端点写清错误码含义(见 `backend/AGENTS.md`),把重复的部分收在这里,
避免十几处各写一份措辞不同的 500/422。这里只有数据与构造函数,不含业务逻辑。
"""

from typing import Any


def json_response(description: str, example: Any) -> dict:
    """带单个示例的 JSON 响应注解,示例形状与端点真实返回保持一致。"""
    return {
        "description": description,
        "content": {"application/json": {"example": example}},
    }


def json_response_examples(description: str, examples: dict[str, dict]) -> dict:
    """一个端点有多种响应形态时(例如澄清/生成两种回复),用 examples 并列展示。"""
    return {
        "description": description,
        "content": {"application/json": {"examples": examples}},
    }


def named(summary: str, value: Any, description: str = "") -> dict:
    """OpenAPI examples 里的单条示例。"""
    item: dict = {"summary": summary, "value": value}
    if description:
        item["description"] = description
    return item


def error_response(description: str, detail: Any) -> dict:
    """错误响应注解:FastAPI 的错误体形状固定为 {"detail": ...}。"""
    return json_response(description, {"detail": detail})


def internal_error(detail: str = "Internal Server Error") -> dict:
    """未捕获异常的统一说明:进程存活但本次请求失败,前端应提示重试。"""
    return error_response("未捕获的服务端错误:进程存活但本次请求失败,前端应提示重试。", detail)


def unconfigured(capability: str) -> dict:
    """外部能力未配置时的错误说明:缺少 Key 又未回落 stub 时由能力工厂抛出。"""
    return error_response(
        f"{capability}未配置:该能力缺 Key 且当前配置未指向可用实现,"
        "请在 .env 或设置中补齐(票 13 落地前只能改配置后重启)。",
        f"{capability}未配置",
    )

VALIDATION_ERROR = error_response(
    "请求校验失败:请求体、表单或路径字段缺失或类型不符",
    [
        {
            "type": "missing",
            "loc": ["body", "messages"],
            "msg": "Field required",
        }
    ],
)
