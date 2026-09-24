"""OpenAPI 契约测试:接口纪律的可执行版本(见 backend/AGENTS.md「接口纪律」)。

OpenAPI 是接口文档的唯一事实源,注解缺失 = 文档缺失。本文件遍历
`app.openapi()` 的每个 operation,断言:

1. 每个端点带 `summary`、描述与 `tag`;
2. 每个端点至少有一处请求或响应示例;
3. 每个端点至少记录一个错误响应(>=400)且带说明文字;
4. 全部端点都被 `tag` 覆盖,且顶层声明的 tag 分组都有描述、都不空置;
5. 应用里全部 `APIRoute` 都出现在 schema 中(没有端点被静默排除出文档)。
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.main import app

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _collect_operations() -> list[tuple[str, str, dict]]:
    schema = app.openapi()
    return [
        (path, method, operation)
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]


def _has_example(payload: dict | None) -> bool:
    """payload 为 requestBody 或单个 response:含 example(s) 即算有示例。"""
    if not isinstance(payload, dict):
        return False
    for media in (payload.get("content") or {}).values():
        if not isinstance(media, dict):
            continue
        if media.get("example") is not None or media.get("examples"):
            return True
        schema = media.get("schema")
        if isinstance(schema, dict) and schema.get("example") is not None:
            return True
    return False


def _has_request_example(operation: dict) -> bool:
    return _has_example(operation.get("requestBody"))


def _has_response_example(operation: dict) -> bool:
    return any(_has_example(r) for r in (operation.get("responses") or {}).values())


OPERATIONS = _collect_operations()
IDS = [f"{method.upper()} {path}" for path, method, _ in OPERATIONS]


def test_endpoint_inventory_is_not_empty():
    """盘点基线:接口全部被注解的前提是 schema 里确实有端点。"""
    assert len(OPERATIONS) >= 15, f"OpenAPI 只暴露了 {len(OPERATIONS)} 个 operation"


@pytest.mark.parametrize(("path", "method", "operation"), OPERATIONS, ids=IDS)
def test_operation_documented(path: str, method: str, operation: dict):
    """接口纪律:summary + 描述 + tag 齐备,且至少一处请求/响应示例。"""
    missing = [
        field
        for field, value in (
            ("summary", operation.get("summary")),
            ("description", operation.get("description")),
        )
        if not (value or "").strip()
    ]
    assert not missing, f"{method.upper()} {path} 缺注解: {', '.join(missing)}"
    assert operation.get("tags"), f"{method.upper()} {path} 未分组: 缺 tag"
    assert _has_request_example(operation) or _has_response_example(operation), (
        f"{method.upper()} {path} 没有任何请求或响应示例"
    )


@pytest.mark.parametrize(("path", "method", "operation"), OPERATIONS, ids=IDS)
def test_operation_documents_error_code(path: str, method: str, operation: dict):
    """接口纪律:每个端点至少记录一个错误响应,并写明含义。"""
    errors = {
        code: response
        for code, response in (operation.get("responses") or {}).items()
        if code.isdigit() and int(code) >= 400
    }
    assert errors, f"{method.upper()} {path} 未记录任何错误码"
    for code, response in errors.items():
        assert (response.get("description") or "").strip(), (
            f"{method.upper()} {path} 的 {code} 错误码没有说明"
        )


def test_every_operation_is_tagged_and_groups_are_declared():
    """全部端点都被 tag 覆盖;顶层声明的分组都有描述,且不空置。"""
    schema = app.openapi()
    declared = {tag["name"] for tag in schema.get("tags") or []}
    assert declared, "OpenAPI 未声明任何 tag 分组(顶层 tags 缺失)"

    used = set()
    for path, method, operation in OPERATIONS:
        tags = operation.get("tags") or []
        assert tags, f"{method.upper()} {path} 未被 tag 覆盖"
        for tag in tags:
            assert tag in declared, f"{method.upper()} {path} 用了未声明的 tag: {tag}"
            used.add(tag)

    assert declared - used == set(), f"空置的 tag 分组: {sorted(declared - used)}"


def test_declared_tags_have_descriptions():
    """Swagger/ReDoc 里每个分组都要有说明,前端才拿得到导航语义。"""
    for tag in app.openapi().get("tags") or []:
        assert (tag.get("description") or "").strip(), f"tag {tag['name']} 缺描述"


def test_no_route_is_hidden_from_the_schema():
    """无端点被静默排除:应用里的 APIRoute 必须都在 schema 中。"""
    documented = {
        (path, method.upper()) for path, method, _ in OPERATIONS
    }
    actual = {
        (route.path, method.upper())
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
        if method.lower() in HTTP_METHODS
    }
    assert actual - documented == set(), (
        f"以下端点未出现在 OpenAPI: {sorted(actual - documented)}"
    )
