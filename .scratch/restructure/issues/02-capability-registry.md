# 02: 能力注册统一

**What to build:** 换任何云端能力只改配置不改代码。对话与向量化收敛为单一 OpenAI 兼容 provider——填 base_url / 模型名 / Key 即可在 dashscope、deepseek、硅基流动之间切换；向量化从对话 provider 拆成独立接口与工厂；语音转写与网络搜索补齐「接口 + 必有 stub」（搜索此前只有写死的客户端、无兜底）；PDF 解析提供 mineru / pypdf / mineru 失败退 pypdf 三种可选策略，替换写死在解析类里的兜底。对教师行为不变；无 Key 的 stub 模式仍是全链路底线。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] 五项能力（对话 / 向量化 / 语音转写 / PDF 解析 / 网络搜索）都是接口 + 按配置选择的工厂，新增实现无需改动调用方
- [x] OpenAI 兼容 provider 经 MockTransport 契约测试覆盖三家方言各一例
- [x] 向量化是独立接口，调用方不再依赖对话 provider
- [x] PDF 三策略可经配置切换，失败兜底行为有测试
- [x] stub 模式全链路可跑（既有底线测试保持绿）

## 交付记录

**分支**：`JulianZBY/issue-02-capability-registry`
**commit**：`refactor(02): 能力注册统一`。代码与测试所在的提交对象 = `1145e8b`（用 `git show 1145e8b --stat` 核对）；本次收尾的同信息提交只改本交付记录。未 push、未开 PR、未 merge。
（说明：交付记录要写「自己的 sha」会自相矛盾——写进去 sha 就变了，所以这里的 sha 指向内容为「代码 + 测试 + 记录初版」的那个提交对象。）

### 设计一句话

五项能力共用一份「配置名 → 构造器」注册表（`app/core/registry.py`）：换实现只改配置名 / Key，
实现类只在各自能力包内被 import，调用方只依赖接口 + 工厂。

### 新增文件

| 文件 | 作用 |
| --- | --- |
| `app/core/registry.py` | 注册表（`build` / `register`），未注册的名字报可选项清单 |
| `app/core/dialects.py` | OpenAI 兼容方言预设：dashscope / deepseek / siliconflow 的 base_url + 模型名 + Key 字段 |
| `app/core/llm/providers/openai_compat.py` | 唯一对话/多模态实现，构造参数 = `base_url` + `model` + `api_key`（+ `vision_model`） |
| `app/core/embedding/{base,stub,hash,openai_compat,factory}.py` | 向量化独立接口 + 工厂（stub 8 维 / hash 64 维 crc32 兜底 / OpenAI 兼容） |
| `app/core/search/{base,stub,factory}.py` | 网络搜索接口 + 必有 stub（此前只有写死的 bocha 客户端、无兜底） |
| `app/core/parser/{base,pypdf,fallback,factory}.py` | PDF 接口 + 三策略（mineru / pypdf / mineru_then_pypdf） |
| `tests/test_openai_compat_contract.py` | 10 例：三家方言各一例（MockTransport）+ 配置切换装配 |
| `tests/test_embedding_registry.py` | 9 例：stub / hash 确定性 + 工厂跟随方言与显式覆盖 |
| `tests/test_pdf_strategy.py` | 8 例：三策略各一例 + mineru 失败退 pypdf（云端 failed 与缺 token 两条路径） |
| `tests/test_capability_registry.py` | 11 例：五项能力各证「新增实现无需改动调用方」+ 不变式（调用方不 import 具体实现） |

### 改动文件

- `app/config.py`：新增 `LLM_BASE_URL/LLM_MODEL/LLM_API_KEY/LLM_VISION_MODEL`、`EMBEDDING_*`（provider/base_url/model/api_key/dimensions）、`SEARCH_PROVIDER`、`PDF_STRATEGY`。两处「留空」语义为**保持既有 .env 行为**：`EMBEDDING_PROVIDER` 留空 = 跟随对话方言（deepseek 无硅基流动 Key 时退本地 hash 64 维）；`SEARCH_PROVIDER` 留空 = 有 `BOCHA_API_KEY` 走 bocha，否则 stub。
- `app/core/llm/factory.py`、`app/core/asr/factory.py`：换成注册表选实现（`LLM_BUILDERS` / `ASR_BUILDERS`）。
- `app/core/llm/base.py`：`embed` 从对话接口移出（并入 `Embedder`）；`llm/providers/dashscope.py`、`llm/providers/deepseek.py` 删除（方言差异进 `dialects.py` + `openai_compat.py`）。
- 调用点最小替换（未重排 import、未动端点路径与响应结构）：`app/core/orchestrator.py`、`app/knowledge/pipeline.py`、`app/knowledge/conflict.py`、`app/knowledge/parsers/pdf.py`，以及 `app/api/v1/knowledge.py`（两行 import + 三处调用，端点与响应模型一字未动）。
- `app/core/parser/mineru.py`：实现 `PdfParser` 接口、补 transport 测试缝、本地读文件给可读错误。
- 测试适配：`test_audio` / `test_conflict` / `test_knowledge` / `test_web_search` / `test_graph_retrieval` / `test_llm_stub` 的补丁点从 `get_llm().embed` 迁到 `get_embedder()`；删除 `tests/test_llm_deepseek.py`（该 provider 已并入 openai_compat，用例迁进新契约测试）。
- **审查修正（自查发现）**：`test_reference` / `test_exam_api` / `test_ppt_theme` / `test_interactive_api` 四处仍用旧的 `factory_module.get_llm` 补丁“代为”固定检索向量——重构后这已是空操作，测试会隐式依赖环境默认向量化 provider（开发者 .env 非 stub 时，已种入的 8 维向量会与真实 provider 维度冲突）。已改为在 Embedder 工厂上打补丁（与 `test_audio` / `test_graph_retrieval` 一致），并验证整套检索类用例在 `LLM_PROVIDER=deepseek`（向量化退 64 维 hash）下依然全绿。
- `backend/scripts/verify_services.py`：原脚本 import 了已删除的 `providers.dashscope` / `BochaSearchClient`，重构后会 ImportError；改为按配置装配 `get_llm()/get_embedder()/get_search()/get_pdf_parser()`（顺带成了配置口径的真实验证入口）。**小越界说明**：所有权清单未列 `scripts/`，但该文件是本次删除的 provider 的调用点，不修即坏。
- `backend/.env.example`：补新配置项说明。**小越界说明**：所有权清单未列此文件，但它是配置的唯一文档面，否则新增配置无处可查；只做追加/改注释，未动键名默认值语义。

### 可观测验收

```text
$ uv run pytest -q
128 passed, 2 warnings in 3.20s        # 基线 95 → 净 +33（删 6 条已迁移用例，新增 39 条）
$ uv run ruff check .                 # backend/AGENTS.md 记录的 lint 命令口径
All checks passed!

# 抗环境干扰（审查修正的验证）：开发者 .env 非 stub 时检索类用例仍确定性全绿
$ $env:LLM_PROVIDER='deepseek'; $env:DEEPSEEK_API_KEY='sk-demo'; $env:SILICONFLOW_API_KEY=''
$ uv run pytest -q tests/test_reference.py tests/test_graph_retrieval.py tests/test_ppt_theme.py \
    tests/test_exam_api.py tests/test_interactive_api.py tests/test_knowledge.py \
    tests/test_audio.py tests/test_conflict.py
43 passed
```

新增契约测试（`--collect-only` 计数）：`test_openai_compat_contract.py` 10、`test_embedding_registry.py` 9、`test_pdf_strategy.py` 8、`test_capability_registry.py` 11。

#### 「只改配置即可切换」证据（同一份代码，只设环境变量）

```text
# 1) LLM_PROVIDER=stub（无 Key 底线）
$ $env:LLM_PROVIDER='stub'; uv run python -c "...get_llm()/get_embedder()"
llm   = StubProvider
embed = StubEmbedder
$ uv run pytest tests/test_llm_stub.py tests/test_chat.py tests/test_capability_registry.py -q
16 passed

# 2) PDF_STRATEGY=pypdf
$ $env:PDF_STRATEGY='pypdf'; uv run python -c "..."
策略实例 = PypdfParser name = pypdf
调用方解析结果 = TCP three-way handshake curriculum
$ uv run pytest tests/test_pdf_strategy.py -q
8 passed

# 3) PDF_STRATEGY=mineru_then_pypdf（无 MINERU_TOKEN → mineru 失败退 pypdf）
$ $env:PDF_STRATEGY='mineru_then_pypdf'; $env:MINERU_TOKEN=''; uv run python -c "..."
策略实例 = FallbackPdfParser name = fallback
PDF 主策略 mineru 失败，退到 pypdf      # logger.warning(exc_info=True) 的预期输出
调用方解析结果 = TCP three-way handshake curriculum
$ uv run pytest tests/test_pdf_strategy.py -q
8 passed

# 4) 附加：同一份代码在方言间切换（仅改环境变量）
$ LLM_PROVIDER=dashscope  → llm: https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus | vision: qwen-vl-max
                            embed: .../compatible-mode/v1 | text-embedding-v3 | dim: 1024
$ LLM_PROVIDER=deepseek（无 SILICONFLOW_API_KEY）→ llm: https://api.deepseek.com | deepseek-chat | vision: (无)
                            embed: HashEmbedder（本地 crc32 兜底）
$ LLM_PROVIDER=deepseek + SILICONFLOW_API_KEY → embed: https://api.siliconflow.cn/v1 | BAAI/bge-large-zh-v1.5
$ EMBEDDING_PROVIDER=openai + EMBEDDING_BASE_URL/MODEL/API_KEY/DIMENSIONS
                            → embed: https://llm.example.edu/v1 | edu-embed-1024 | dim: 1024
```

（无 Key 环境：上面 4a–4d 只打印解析出的实例与 base_url，不发真实请求；云端契约全部由 `httpx.MockTransport` 覆盖。）

### 验收项 → 测试映射

| 票面要求 | 落点 |
| --- | --- |
| 1 对话收敛为单一 OpenAI 兼容 provider（base_url + model + api_key） | `llm/providers/openai_compat.py` + `dialects.py`；`test_openai_compat_contract.py::test_factory_switches_dialect_from_config_only` / `test_config_override_reaches_any_openai_compatible_server` |
| 2 向量化独立接口与工厂 | `core/embedding/*`；`test_embedding_registry.py`（跟随方言 / 显式覆盖 / hash 兜底） |
| 3 ASR 接口 + factory + stub | `core/asr/{base,stub,paraformer,factory}.py`；`test_audio.py` 的 paraformer MockTransport 契约 + `test_capability_registry.py` 可插拔 |
| 4 网络搜索接口 + factory + 必有 stub | `core/search/{base,stub,bocha,factory}.py`；`test_web_search.py`（配置实现 + stub 底线） |
| 5 PDF 三策略经配置切换 | `core/parser/{base,pypdf,mineru,fallback,factory}.py`；`test_pdf_strategy.py` |
| 6 三家方言 MockTransport 契约 | `test_openai_compat_contract.py`（dashscope 多模态 payload / deepseek 纯文本 / 硅基流动 embeddings + 响应乱序按 index 还原） |
| 6 PDF 三策略 + 失败兜底 | `test_pdf_strategy.py::test_mineru_strategy_runs_full_cloud_flow` / `test_pypdf_strategy_reads_local_text_layer` / `test_mineru_failure_falls_back_to_pypdf` / `test_mineru_missing_token_falls_back_to_pypdf` |
| 7 五项能力「新增实现无需改动调用方」 | `test_capability_registry.py`（5 例注册新实现后从调用方观测 + 1 例不变式扫描） |

### 自审（Standards / Spec 两轴）

方式：本 worker 无子代理能力，两轴自查由本人按 `code-review` 技能的口径执行（非并行子代理）。

**Standards**（依据 `backend/AGENTS.md` 分层铁律 + 代码异味基线）

- ✅ 外部能力一律 `core/*/base.py` 接口 + `factory.py` 按配置选择；`api/v1/` 只做校验与转发；OpenAPI 注解未增未减（属并行票 01 的范围）。
- ✅ 无 Key（stub）全链路可跑：128 绿，含既有底线用例。
- ⚠️ **判断项**：铁律写「新实现必须同时提供 stub」，而 PDF 只给 mineru / pypdf / 兜底三策略，没有 `PDF_STRATEGY=stub`。理由：**pypdf 就是 PDF 的无 Key 底线**（本地文本层，不需任何 Key），而 stub 假正文会污染知识库；本票验收项也只列三策略。若要严格对齐铁律，可再加一个只返回占位文本的 `stub` 策略。
- ⚠️ **判断项**：`app/core/dialects.py` 同时被对话与向量化工厂读。它是配置表（base_url / 模型名 / Key 字段），不是 provider 实现依赖，不违反「调用方不 import 具体实现」。
- 未发现重复代码：五处「按配置构造 + 缺 Key 报错」的文法各自成文，共用 `registry.build/register` 收口；无发散式修改、无投机抽象（未加本票没要求的参数）。

#### Spec

- ✅ 七项交付逐条落到可验证结果（见上表）；不变式由 `test_callers_do_not_import_concrete_implementations` 守住。
- ✅ 约束遵守：端点路径与响应结构未变；`api/**` 仅 9 行（两行 import + 三处调用）；`docs/**`、`CONTEXT.md`（本工作树不存在）、`frontend/**` 未动；测试未新建/污染 `data/vectors.db` 与 `uploads`。
- ⚠️ **范围外但必要**：`backend/scripts/verify_services.py`（被删 provider 的调用点，不修即 ImportError）与 `backend/.env.example`（新配置的唯一文档面），各做最小修正，已在「改动文件」标为小越界。
- ⚠️ **默认行为变化（票面要求所致）**：网络搜索缺 Key 时从「报错」变为「stub 占位结果」，已入遗留问题。

### 遗留问题

1. **`data/output` 仍是测试共享落盘**（既有遗留，本票未扩大范围）：跑测试会往 `backend/data/output` 写课件/教案文件；`vectors.db` / `uploads` / 主库继续由 `tests/conftest.py` 隔离，本次验证未新建 `vectors.db`、未污染 `uploads`。
2. **切向量化实现会改变向量维度**：维度冲突仍靠 `VectorStore._dim_mismatch` 报人话提示，需删 `vectors.db` 重建（既有行为）。`EMBEDDING_PROVIDER` 留空的「跟随方言」是隐式规则，已在 `config.py` 注释与 `.env.example` 写明。
3. **未做真实云端联通性验证**（本工作树无任何 Key）：dashscope / deepseek / siliconflow / mineru / bocha 全部走 stub + MockTransport；也未在浏览器/前端验证。
4. **`SEARCH_PROVIDER` 默认语义变化**：未配 Key 时从「请求报错」变为「stub 占位结果」（本票要求），占位结果带 `（stub 网络搜索）` 标记与 `https://example.com/stub/*` 假链接，不会冒充真实资料。
5. 既有未实现、本票未扩大范围：embedding 批量分片（dashscope 单请求 10 条上限）、多模态 embedding、`/embeddings` 失败重试。
