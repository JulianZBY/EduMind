# 05: 会话持久层 + 状态机收编

**What to build:** 让后端成为备课会话的唯一事实源，并把对话状态机从路由层收进核心层。会话与消息落库，教师换设备、清浏览器数据后历史不丢；澄清→检索→生成→反馈 的流转、追问粒度与跳过追问的判断都不再住在路由里；意图按会话增量累积，不再每轮把全部对话重析一遍；「跳过追问」改为语义判定，不再依赖硬编码子串词表。本票交付到 HTTP 层可演示（会话创建 / 列表 / 历史 / 重命名 / 删除）。

**Blocked by:** 03 RAG 策略收编

**Status:** ready-for-agent

- [x] 会话 API：创建 / 列表 / 历史 / 重命名 / 删除，全部经 HTTP 缝测试
      （`POST /api/v1/sessions`、`GET /api/v1/sessions`、`GET|PATCH|DELETE /api/v1/sessions/{session_id}`；
      `backend/tests/test_sessions_api.py` 12 个用例全绿，逐条名字与结果见交付记录「证据 1」）
- [x] 同一会话多轮对话意图增量累积，行为有测试对比
      （`core/conversation.accumulate_intent` = 上一轮意图 + 本轮新增；
      `test_session_intent_accumulation_matches_full_reanalysis` 与
      `test_incremental_intent_analyzes_only_the_new_turn`，证据见「证据 2」）
- [x] 跳过追问为语义化判定，行为有测试
      （`core/clarify.should_skip_clarification` 走 LLM 语义判定，`_SKIP_WORDS` 已删；
      正反例见「证据 3」）
- [x] 澄清与追问判断逻辑不再出现在路由层
      （`app/api/v1/chat.py` 只剩参数校验 + 转发；守卫用例
      `test_api_layer_holds_no_clarify_or_skip_judgement` 全绿）
- [x] 测试只断言 API 响应与数据变迁，不断言内部函数调用
      （新用例断言响应字段、消息落库行、会话意图列；被替换的只有 LLM **能力**替身
      `tests/session_support.py::SemanticLLM`，经能力注册表挂上）

## 交付记录

**一句话**：备课会话与消息落进 `prep_sessions` / `session_messages` 两张新表，会话 CRUD 走五个新端点；
对话状态机（澄清 → 检索 → 生成 → 反馈）、追问粒度、跳过追问的语义判定与意图增量累积全部收进
`app/core/conversation.py` + `app/core/session_service.py`，路由层只剩参数校验与转发；一次生成回复的
意图分析调用从 2 次降到 1 次，且每轮只分析本轮原话。

**分支 / commit**：`JulianZBY/issue-05-session-persistence`。代码与测试所在的提交对象 = `c3d2b64`
（用 `git show c3d2b64 --stat` 核对，19 个文件）；其后若另有提交，只补本交付记录与 pi-lens 格式化，不动代码。
基线 `beedb64`（票 03 合入后的工作树尖端）。未 push、未开 PR、未 merge/rebase。

**新增文件**

| 文件 | 职责 |
| --- | --- |
| `backend/app/db/sessions.py` | 持久层 `ConversationStore`：会话 / 消息的 ORM 读写（无业务判断） |
| `backend/app/core/conversation.py` | 对话状态机：意图累积、澄清 → 检索 → 生成 → 反馈、两种回复形态 |
| `backend/app/core/session_service.py` | 会话用例：创建 / 列表 / 历史 / 更新 / 删除 + 一轮对话落库 |
| `backend/app/api/v1/sessions.py` | 五个会话端点（完整 OpenAPI 注解，tag = 备课会话） |
| `backend/tests/test_sessions_api.py` | 会话 API 的 HTTP 缝用例（12 个） |
| `backend/tests/test_session_turns.py` | 一轮对话行为用例（11 个：持久化 / 粒度 / 语义跳过 / 意图累积 / 守卫） |
| `backend/tests/session_support.py` | LLM 能力替身（语义网关）+ 提示词观测助手 |

**改动**

- `backend/app/db/models.py`：新增 `PrepSession`（标题 / 追问粒度 / 累积意图 / 参考资料，字段带中文语义注释，
  `user_id="default"`）与 `SessionMessage`（会话内序号 / role / 原话 / 回复形态 / 生成物），消息随会话级联删除；
  模块 docstring 的断链 `DESIGN.md §3.3`（票 01 登记的遗留）改为指向仓库内真实存在的
  `backend/AGENTS.md` / `docs/architecture.md` / `docs/adr/0002-backend-source-of-truth.md`。
- `backend/app/api/v1/chat.py`：删掉路由层的澄清判断与 `_SKIP_WORDS` 词表，路由只做参数校验与转发；
  `ChatRequest` **纯新增**可选字段 `session_id`，`ChatResponse` **纯新增**字段 `session_id`（无状态请求为
  `null`）；既有字段语义与路径未动。
- `backend/app/api/v1/router.py`：挂上会话路由（一行）。
- `backend/app/core/intent.py`：新增 `merge_intent`（增量累积提示词，只喂「已累积意图 + 本轮新增」）；
  `analyze_intent`（全量重析）保留为无状态路径。
- `backend/app/core/clarify.py`：新增 `should_skip_clarification`（语义判定，LLM 输出不可解析时保守地继续追问）。
- `backend/app/core/orchestrator.py`：`orchestrate(intent, …)` 改为接收累积意图，不再自带一次意图分析。
- `backend/app/core/llm/providers/stub.py`：补语义判定分支（stub 不跳过追问，由意图完整性决定，不误跳过）。
- `backend/tests/conftest.py`：新增两个夹具（`install_semantic_llm` 能力替身、`isolated_output_dir` 落盘隔离），
  原有落盘隔离不变。
- `backend/tests/test_chat.py`：改走能力替身接缝（不再替换内部函数），三个分支断言不变。
- `backend/tests/test_reference.py` / `test_graph_retrieval.py` / `test_ppt_theme.py`：仅把「伪装意图分析」的
  接缝从 `api.v1.chat` / `core.orchestrator` 改到 `core.conversation`（收编后意图分析的新家），断言未动。

**跑过的命令与结果**

```text
cd backend
uv sync                                     # 全新工作树，无 setup 钩子
uv run pytest -q                            # 214 passed（基线 181：+23 本票用例 +10 新端点自动进 OpenAPI 契约用例）
uv run ruff check .                         # All checks passed!
uv run pytest tests/test_sessions_api.py tests/test_session_turns.py -q
                                            # 23 passed
uv run pytest tests/test_openapi_contract.py -q
                                            # 全绿（含 5 个新端点 × documented / error_code 两个断言）
```

**证据 1：五个会话 API 的用例与结果**（`uv run pytest tests/test_sessions_api.py tests/test_session_turns.py -v`）

| 动作 | 端点 | 用例（全部 PASSED） |
| --- | --- | --- |
| 创建 | `POST /api/v1/sessions` | `test_create_session_returns_teacher_facing_summary`、`test_create_session_defaults_title_and_granularity`、`test_create_session_rejects_unknown_granularity` |
| 列表 | `GET /api/v1/sessions` | `test_list_sessions_orders_recent_first_and_filters_by_keyword`（最近使用在前 + `q` 标题检索） |
| 历史 | `GET /api/v1/sessions/{session_id}` | `test_history_returns_session_with_messages_in_order`、`test_history_of_unknown_session_returns_404`、`test_session_turns_persist_history_for_other_devices`（换设备回看完整四轮） |
| 重命名 | `PATCH /api/v1/sessions/{session_id}` | `test_rename_session_updates_title_and_settings`、`test_rename_unknown_session_returns_404`、`test_update_without_any_field_is_rejected`、`test_rename_to_blank_title_is_rejected` |
| 删除 | `DELETE /api/v1/sessions/{session_id}` | `test_delete_session_removes_session_and_messages`（消息一并消失、不留孤儿）、`test_delete_unknown_session_returns_404` |

接口纪律由既有契约用例逐端点把关，新端点同样通过：
`test_operation_documented[POST /api/v1/sessions]`、`[GET /api/v1/sessions]`、
`[GET /api/v1/sessions/{session_id}]`、`[PATCH /api/v1/sessions/{session_id}]`、
`[DELETE /api/v1/sessions/{session_id}]` 及对应 `test_operation_documents_error_code[...]` —— 10 个用例全 PASSED。

**证据 2：意图增量累积 vs 全量重析**

行为对比（`test_session_intent_accumulation_matches_full_reanalysis` PASSED）：同一段两轮表述，会话路径
（增量合并）与无状态路径（整段重析）产出的 `artifacts.intent` 在关键字段上逐项相等：
`topic=一次函数 / grade=初二 / duration_minutes=40 / objectives=[理解一次函数的图象] /
style=情境导入 / key_points=[斜率与图象]`——即累积结果既不丢第一轮的要素，也不用重析全部历史。

调用与输入量证据（`test_incremental_intent_analyzes_only_the_new_turn` PASSED）：两轮会话恰好 2 次意图分析
（每轮 1 次），第 2 轮的分析输入**就是本轮原话**（不含第 1 轮表述）；全量重析路径的分析输入是整段历史，
文本量明显更大。

「调用次数下降」的实测（同一条探针脚本，分别跑在基线提交与当前工作树；探针用能力注册表挂计数网关，
不改任何内部函数）：

```text
收编前（beedb64，临时 worktree）：{"intent_calls": 2, "skip_calls": 0, "generate_calls": 3}
收编后（本工作树）            ：{"intent_calls": 1, "skip_calls": 0, "generate_calls": 3}
```

即一次生成回复的意图分析调用 **2 → 1**（收编前路由析一次、编排器再析一次；现在状态机析一次后把累积意图
交给编排器），生成调用数不变（3）。

**证据 3：跳过追问语义化（正反例）**

- 正例 `test_skip_clarification_accepts_a_synonym_phrasing`（PASSED）：教师说
  「需求都清楚了，别再问了，直接给我结果」——不含旧词表（`开始生成/就这样/生成吧/够了/可以了/直接生成`）
  的任何子串，语义判定为跳过 → `clarifying=false` 直出生成物（旧实现会继续追问）。
- 反例 `test_negated_generation_is_not_treated_as_skip`（PASSED）：教师说
  「现在可以了，不过我还想补充教学目标」——字面含旧词表命中的「可以了」（旧实现会当跳过），语义判定
  为「没跳过」→ `clarifying=true` 继续追问，且判定输入就是本轮原话本身。

**证据 4：路由层不再有澄清 / 追问判断**

守卫用例 `test_api_layer_holds_no_clarify_or_skip_judgement`（PASSED）：扫描 `backend/app/api/**` 全部
`.py`，断言不出现 `missing_fields` / `build_question` / `FIELD_QUESTIONS` / `GRANULARITY_FIELDS` /
`should_skip_clarification` / `_SKIP_WORDS` / `analyze_intent` / `orchestrate`（写法对齐票 03 的
`test_orchestrator_has_no_retrieval_details`）。断链修正用例
`test_db_models_docstring_points_to_existing_docs`（PASSED）同时守住「模型文件的文档指针必须可达」。

**缺省行为说明（`POST /api/v1/chat` 新增可选字段 `session_id`）**

- 不传 `session_id`：保持收编前的无状态行为——整段历史由调用方带上、每轮全量重析意图、不落库，
  响应里 `session_id` 为 `null`（`test_chat_without_session_stays_stateless` PASSED）。
- 传 `session_id`：会话成为事实源——`messages` 里最后一条教师消息是本轮新增需求，其余以服务端历史为准；
  追问粒度与参考资料取会话上的设置（改它们用 `PATCH /sessions/{id}`），请求里的 `granularity` /
  `reference_doc_ids` 不生效；会话不存在返回 404，`messages` 里没有教师消息返回 422。

**两轴自审**

- Standards：分层铁律（api 只校验与转发 / 状态机与业务判断住 core / 新表进 `db/models.py` 且字段带中文语义
  注释 / 单用户 `user_id="default"`）；OpenAPI 纪律（5 个新端点带 summary、描述、请求与响应示例、错误码、tag）；
  `uv run ruff check .` 干净；测试只替换 LLM **能力**（能力注册表 + 配置选择，同票 02/03 口径），断言只看
  HTTP 响应与库内数据变迁；面向教师的文案用 CONTEXT.md 术语（新的备课会话 / 澄清回复 / 生成回复 / 追问粒度 /
  跳过追问 / 参考资料）。
- Spec：五条验收项逐条落地（见上方勾选与证据 1–4）；未越界——未改 `app/knowledge/**`、`app/generate/**`、
  `docs/**`、`CONTEXT.md`、`frontend/**`、`.scratch/**` 里非本票文件；既有端点路径与既有字段语义未变
  （`/chat` 只新增可选字段）；测试落盘隔离实测零新增文件（跑本票用例前后 `backend/data/` 文件数 99 → 99）。

**遗留 / 注意事项**

1. 会话列表与历史未分页：单用户本地库量级可控，会话多时列表全量返回（后续需要再补）。
2. 历史接口会随生成回复回传 `messages[].artifacts`（含教案完整结构），长会话响应偏大；生成物版本接口
   （票 07）落地后可由前端按需取用。
3. 语义判定只在「要素不全」时触发，每次多花一次 LLM 调用；stub 模式不跳过追问（追问与否由意图完整性决定），
   无 Key 时链路仍可跑。
4. 会话内上传文档自动归入该会话参考资料（票 06 的用户故事）未在本票实现：后端已提供 `PATCH /sessions/{id}`
   与创建时的 `reference_doc_ids`，绑定动作留票 06。
5. 生成物全版本留痕（版本表、下载、以历史版本为基线）归票 07；本票只落消息与累积意图。
6. `POST /chat` 响应新增 `session_id: null` 字段：对既有调用方是纯增量（既有字段仍在、语义未变）。
