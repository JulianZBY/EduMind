# EduMind 后端规范

FastAPI + pydantic v2 + SQLAlchemy 2(同步)+ SQLite/sqlite-vec,Python ≥ 3.11,uv 管依赖。

## 命令

```bash
uv sync                                              # 装依赖
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run pytest                                        # 测试
uv run ruff check .                                  # lint
```

## 分层铁律

- `api/v1/` 只做参数校验与转发;业务逻辑住 `core/`(对话状态机 = `core/`,不进路由)。
- 外部能力(LLM 对话/嵌入/ASR/PDF/搜索/检索/分块)一律走 `core/*/base.py` 接口 + `factory.py` 按配置选择;**新实现必须同时提供 stub**。能力清单见 ADR-0003。
- 知识引擎住 `knowledge/`(RAG 策略接口在此);生成器住 `generate/`。
- 新表进 `db/models.py`,字段带中文语义注释;单用户 `user_id="default"`。

## 接口纪律(OpenAPI 是接口文档唯一事实源)

每个端点必带:`summary`、描述、请求/响应 `examples`、错误码、`tag` 分组。前端 TS 类型由 schema 生成——**注解缺失 = 文档缺失**。破坏性变更才升 `/api/v2`。

## 测试

- 改动配 pytest;**无 Key(stub 模式)全链路必须可跑**,破坏即阻塞。
- 面向教师的字符串用 `CONTEXT.md` 词汇。
