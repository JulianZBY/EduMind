# 03: RAG 策略收编

**What to build:** 检索与分块成为可插拔策略：Retriever 两个实现（纯向量 / 向量 + 图谱融合）与 Chunker 接口化并纳入能力注册；检索逻辑从编排器移进策略实现，编排器只消费策略结果。默认档行为与收编前完全一致，后续加重排或换分块方式只动策略、不动引擎躯干。

**Blocked by:** 02 能力注册统一

**Status:** done

- [x] Retriever / Chunker 接口 + 两实现，配置按名切换
      （`RETRIEVAL_STRATEGY` = `vector_graph`（默认）/ `vector`；`CHUNK_STRATEGY` = `paragraph`，
      既有分块逻辑即这一格的实现）
- [x] 编排器内不再有检索细节（参考资料加权、图谱邻接融合、来源溯源都归策略）
      （`backend/app/core/orchestrator.py` 现只剩意图 → 策略 → 生成，检索细节全在
      `app/knowledge/retrieval/`；不变式用例 `test_orchestrator_has_no_retrieval_details` 守住）
- [x] 默认配置下检索行为与收编前一致（既有图谱检索测试保持绿）
      （黄金比对 `test_default_retrieval_matches_pre_refactor_golden` 逐字段对齐收编前输出；
      既有 `test_graph_retrieval.py` / `test_reference.py` 断言未改，全绿）
- [x] 两种检索策略的行为差异经 API 可观测并有测试
      （新端点 `POST /api/v1/knowledge/retrieve`，纯新增；
      `test_two_strategies_differ_over_http` 两次配置下的响应见下方交付记录）

## 交付记录

**一句话**：编排器现在只剩「意图分析 → 按配置取检索策略 → 并发生成产物」，检索细节（参考资料加权、
图谱邻接融合、来源溯源、上下文预算内组装）全部搬进 `app/knowledge/retrieval/` 的策略实现，
后续加重排只需在 `RETRIEVER_BUILDERS` 注册新实现。

**分支 / commit**：`JulianZBY/issue-03-rag-strategies`。代码与测试所在的提交对象 = `98597c2`
（用 `git show 98597c2 --stat` 核对，19 个文件）；其后还有两个同信息提交，
只补本交付记录与 `backend/.env.example` 的新配置样例，不动代码。未 push、未开 PR、未 merge/rebase。
基线 `1f39891`。

**新增文件**

| 文件 | 职责 |
| --- | --- |
| `backend/app/knowledge/chunking/base.py` | `Chunker` 接口 |
| `backend/app/knowledge/chunking/paragraph.py` | `paragraph` 实现（收编前的 `chunk_text` 逻辑 + 纯函数保留） |
| `backend/app/knowledge/chunking/factory.py` | `CHUNKER_BUILDERS` + `get_chunker()` |
| `backend/app/knowledge/chunking/__init__.py` | 包入口（仍导出 `chunk_text` 等，既有 import 不变） |
| `backend/app/knowledge/retrieval/base.py` | `Retriever` 接口 + `RetrievalHit` / `RetrievalResult` |
| `backend/app/knowledge/retrieval/search.py` | 公共前半段：意图 → 查询串 → 向量化 → 参考资料加权 KNN；来源资料名溯源 |
| `backend/app/knowledge/retrieval/context.py` | 预算内上下文组装（收编前规则逐字保留）+ `CONTEXT_BUDGET_CHARS` |
| `backend/app/knowledge/retrieval/vector.py` | `vector` 实现（纯向量） |
| `backend/app/knowledge/retrieval/vector_graph.py` | `vector_graph` 实现（默认档，向量 + 图谱邻接融合） |
| `backend/app/knowledge/retrieval/factory.py` | `RETRIEVER_BUILDERS` + `get_retriever()` |
| `backend/tests/test_rag_strategies.py` | 本票测试（13 个用例函数 → 15 个 test item，含黄金比对与两档 HTTP 差异） |

**改动 / 删除**

- `backend/app/knowledge/chunking.py` → 拆为上面的 `chunking/` 包（删除原文件，逻辑逐字保留）。
- `backend/app/knowledge/pipeline.py`：分块调用点 `chunk_text(result)` → `get_chunker().chunk(result)`。
- `backend/app/core/orchestrator.py`：删去 `retrieve_knowledge` / `_source_names` / `_fused_context` / `_assemble_context`
  与预算常量，改 `get_retriever().retrieve(intent, reference_doc_ids=...)`。
- `backend/app/api/v1/exam.py`、`backend/app/api/v1/interactive.py`：各两行（import + 调用点）改走工厂。
- `backend/app/api/v1/knowledge.py`：**纯新增** `POST /api/v1/knowledge/retrieve`（观测端点）+ 两行 import；
  既有端点/字段/注解/文档字符串未动。
- `backend/app/config.py`：新增 `chunk_strategy` / `retrieval_strategy`；`backend/.env.example` 同步（唯一文档面）。
  两文件不在本票声明的 ownership 通配内，但按配置名切换必须在此落配置项（与票 02 同一处理）。
- `backend/tests/test_graph_retrieval.py`：仅一行 import（`CONTEXT_BUDGET_CHARS` 随策略换家），断言未动。

**跑过的命令与结果**

```text
cd backend
uv sync                                              # 全新工作树，无 setup 钩子
uv run pytest -q                                     # 181 passed（收编前基线 164：+15 本票用例，
                                                     #   +2 新端点自动进入 OpenAPI 契约用例）
uv run ruff check .                                  # All checks passed!
uv run pytest tests/test_graph_retrieval.py tests/test_reference.py \
  tests/test_exam_api.py tests/test_interactive_api.py tests/test_chunking.py -q
                                                     # 22 passed（既有图谱检索/参考资料/生成端点回归）
```

**证据 1：默认档与收编前逐字段一致**

收编前（`1f39891` 代码）用一次性探针捕获 `retrieve_knowledge` 输出，抄成黄金值写进
`test_default_retrieval_matches_pre_refactor_golden`（PASSED），比对项：

```text
context:  "=== 知识片段 ===\n参考片段\n\n片段二\n\n片段一\n\n=== 图谱关联知识点（按知识递进） ===\n【求导法则】求导法则内容"
          收编前 == 收编后（黄金比对为等值断言）
sources:  ["参考.pdf", "讲义.pdf"]                        == 收编前
hits:     [(3,"doc_ref"),(2,"doc_hit","片段二"),(1,"doc_hit","片段一")] == 收编前
          距离 [10.748, 11.031, 11.314] 且参考片段原始距离最大却被加权置首（参考资料加权仍在）
```

收编前探针原始输出（节选）：
`{"context": "=== 知识片段 ===\n参考片段\n\n片段二\n\n片段一\n\n=== 图谱关联知识点（按知识递进） ===\n【求导法则】求导法则内容", "sources": ["参考.pdf", "讲义.pdf"], ...}`

**证据 2：两档策略差异可观测（两次不同配置下的响应）**

```powershell
cd backend
uv run pytest "tests/test_rag_strategies.py::test_two_strategies_differ_over_http" -q -s
```

```text
vector_graph: {"strategy": "vector_graph",
               "context": "=== 知识片段 ===\n参考片段\n\n片段二\n\n片段一\n\n=== 图谱关联知识点（按知识递进） ===\n【求导法则】求导法则内容",
               "sources": ["参考.pdf", "讲义.pdf"],
               "hits": [参考片段(3), 片段二(2), 片段一(1)],
               "graph_nodes": [{"id": "node_b", "title": "求导法则", "content": "求导法则内容"}]}
vector      : {"strategy": "vector",
               "context": "参考片段\n\n片段二\n\n片段一",
               "sources": ["参考.pdf", "讲义.pdf"],
               "hits": [参考片段(3), 片段二(2), 片段一(1)],
               "graph_nodes": []}
```

差异只在图谱融合：`graph_nodes` 有/无、`context` 带不带图谱段；命中分块与来源溯源两档一致（各自正确）。

**证据 2b：走真实配置（环境变量，两个独立进程）的同一差异**

```powershell
cd backend
$env:RETRIEVAL_STRATEGY='vector_graph'; uv run python <同一段种子数据 + POST /api/v1/knowledge/retrieve 脚本>
$env:RETRIEVAL_STRATEGY='vector';       uv run python <同上>
```

```text
RETRIEVAL_STRATEGY=vector_graph
strategy=vector_graph context='=== 知识片段 ===\n导数讲义片段\n\n=== 图谱关联知识点（按知识递进） ===\n【求导法则】邻接内容' \
  sources=['导数讲义.pdf'] graph_nodes=['求导法则']
RETRIEVAL_STRATEGY=vector
strategy=vector context='导数讲义片段' sources=['导数讲义.pdf'] graph_nodes=[]
CHUNK_STRATEGY=nowhere
ValueError: 未实现的分块策略: nowhere（可选：paragraph）
```

**两轴自审**

- Standards：分层铁律（api 只转发 / core 不碰检索细节 / 能力实现住 knowledge 的策略包）、OpenAPI 纪律
  （新端点带 summary/描述/示例/错误码/tag）均满足；`ruff check` 干净；无重复代码（两档共用 `search.py`），
  无中间人（工厂即注册表口径）。
- Spec：四条验收项逐条落地（见上勾选）；无越界（未改 `docs/**`、`CONTEXT.md`、`frontend/**`，
  `api/**` 仅一处纯新增 + 两处最小调用点替换）。

**遗留 / 注意事项**

1. 工厂与票 02 同口径用 `lru_cache`：改配置后需清缓存才换实例（运行时设置写穿即时生效归票 13）。
2. 两档检索与分块都不依赖云端 Key（无 Key 时向量来自 Embedder 的 stub / hash 兜底），
   故未另造 stub 实现——ADR-0003 的 stub 底线由既有 Embedder 兜底满足。
3. `RetrievalResult.graph_nodes` 是「参与上下文组装的候选」，超预算被截断的部分仍会出现在返回值里，
   实际进上下文的内容以 `context` 为准（字段注释已写明）。
4. 上下文预算仍是常量 `CONTEXT_BUDGET_CHARS = 6000`，未配置化（收编前同款；本票不改行为）。
5. `Retriever.retrieve(intent)` 的意图类型只在 `TYPE_CHECKING` 下引用 `app.core.intent.TeachingIntent`，
   运行时 knowledge 层不反依赖 core（分层箭头仍单向）。

## 协调者复核

**结论：通过（含一次同终端续派收尾）。** 复核人 = 协调者（主代理），2026-09-24。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| 接口 + 两实现 + 配置按名切换 | 读 `app/knowledge/retrieval/factory.py`：`RETRIEVER_BUILDERS` 注册 `vector` / `vector_graph`，默认档 `vector_graph`（收编前行为） | 通过 |
| 编排器内不再有检索细节 | 通读 `app/core/orchestrator.py`：只剩 `get_retriever().retrieve(intent, reference_doc_ids=…)` 与 `retrieval.sources`；加权 / 图谱邻接 / 溯源均在策略层 | 通过 |
| 默认档与收编前一致 | 黄金比对用例 `test_default_retrieval_matches_pre_refactor_golden` + 既有 `test_graph_retrieval.py` / `test_reference.py` 未改绿 | 通过 |
| 两策略差异可观测 | 新增纯新增端点 `POST /knowledge/retrieve`（既有端点注解与字段未动）+ `test_two_strategies_differ_over_http` | 通过 |
| 调用方只依赖接口 | `test_callers_only_depend_on_interface_and_factory` 守卫用例 | 通过 |
| 测试与静态检查 | 协调者亲跑 `uv run pytest -q` → **181 passed**（合并前基线 164）、`uv run ruff check .` 干净 | 通过 |

**发现并处置的状态不一致**：worker 报 `worker_done` 之后，pi-lens 的 deferred formatter 又改了 3 个文件且**未提交**（`knowledge.py` / `retrieval/search.py` / `test_rag_strategies.py`，纯折行）。协调者逐处看过 diff 后**同终端续派**（`reused_terminal`）要求其落地为 `b03801b`，并在最终态复跑 181 passed——**使「合并的状态 = 复核过的状态」**。

- **合并点**：`e56d0e3`（`merge(03)`）；合并后 main 复跑 → 181 passed。
- **状态迁移**：`ready-for-agent` → `done`。
- **遗留去向（已登记）**：工厂 `lru_cache` 导致「运行时改配置需清缓存才能换实例」→ 已写入票 13 派发约束（设置写穿即时生效）。
