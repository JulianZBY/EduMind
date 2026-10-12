# EduMind 后端规范

FastAPI + pydantic v2 + SQLAlchemy 2(同步)+ SQLite/sqlite-vec,Python ≥ 3.11;工具链与 venv 由 mise 管,依赖用 pip 按 requirements.txt 装。

## 命令

```bash
mise run setup:backend                               # 装依赖(建 venv + pip install -r requirements.txt)
mise run dev:backend                                 # uvicorn :8000
mise run test:backend                                # pytest
mise run lint:backend                                # ruff
```

## 分层铁律

- `api/v1/` 只做参数校验与转发;业务逻辑住 `core/`(对话状态机 = `core/`,不进路由)。
- 外部能力(LLM 对话/嵌入/ASR/PDF/搜索/检索/分块)一律走 `core/*/base.py` 接口 + `factory.py` 按配置选择;实现未配置时抛 `ProviderNotConfigured`(全局 503 处理器给出面向教师的引导),**禁止任何假数据兜底实现**;测试替身只在 `tests/support/fakes.py`。能力清单见 ADR-0003;**加一家服务商不必改代码**:写 `backend/providers.json`(模板 `providers.example.json`,格式见 `docs/api/provider-config.md`),启动时并进供应商目录。
- 知识引擎住 `knowledge/`(RAG 策略接口在此);生成器住 `generate/`。
- 新表进 `db/models.py`,字段带中文语义注释;单用户 `user_id="default"`。

## 接口纪律(OpenAPI 是接口文档唯一事实源)

每个端点必带:`summary`、描述、请求/响应 `examples`、错误码、`tag` 分组。前端 TS 类型由 schema 生成——**注解缺失 = 文档缺失**。破坏性变更才升 `/api/v2`。

## 测试

- 改动配 pytest;测试必须离线确定性零成本(能力替身走 tests/support),破坏即阻塞。
- 面向教师的字符串用 `CONTEXT.md` 词汇。

## 与 ADR 的关系

- 本文件曾经的「新实现必须同时提供 stub」约定已被**产品去 stub 化**取代,以本文件正文为准;
- ADR-0003 原文末尾的修订小节记录了这次取代,未静默改史。
