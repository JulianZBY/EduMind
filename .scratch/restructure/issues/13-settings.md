# 13: 设置

**What to build:** 像 pi / opencode 一样配置模型：从供应商目录选择并粘贴 API Key 即用，改动无重启即时生效，回读只见掩码；按任务（意图分析 / 生成 / 冲突比对）选模型档位，未设置的任务回落全局默认；可添加自定义 OpenAI 兼容服务（base_url + 模型 ID）；语音转写、PDF 解析策略、网络搜索的切换也在本页。配置库优先于 `.env` 引导默认。采用编辑密度。

**Blocked by:** 02 能力注册统一; 04 前端基座

**Status:** done

- [x] 目录选择 + 填 Key 后无重启即生效（可当场验证 stub → 真实切换）
      （`PUT /api/v1/settings` 写穿 = 校验 → 落库 → 同步进程内配置 → `invalidate_capabilities()`；
      真进程实测：stub → deepseek 后 `GET /settings` 立刻 ready=true / 来源=设置页；
      检索策略写成 vector 后紧接着 `POST /knowledge/retrieve` 返回 `strategy: vector`）
- [x] 任务级模型选择与回落全局默认的行为可见
      （`GET/PUT /settings` 的 `tasks[]` 逐任务给「实际用的模型 + 来源（任务级 / 全局默认）」；
      `test_task_level_models_reach_each_call_site` 断言三条链各自带上自己的档位）
- [x] 自定义 OpenAI 兼容接入（base_url + 模型 ID）可用
      （`llm_provider=custom` + `LLM_BUILDERS` 新增 custom 构造器；模型 ID 不受目录限制）
- [x] Key 全程掩码，任何响应与表单都不回显明文
      （读接口只回 `masked`（尾部若干位）+ `configured`；写入响应同样不含明文；
      `test_key_is_masked_in_every_response` 对 PUT/GET 的原始响应体做 `not in` 断言）
- [x] 无效配置（未知供应商 / 模型）返回明确错误码与信息
      （400 + `detail.code`：unknown_provider / unknown_model / unknown_capability_impl /
      invalid_base_url，`message` 直接给教师看；写入无效时库内一行不动）
- [x] 能力切换（语音转写 / PDF 策略 / 搜索）即时生效
      （另有向量化 / 检索 / 分块同口径可切；可选实现直接来自各能力注册表）

## 交付记录

**一句话**：设置页现在能选供应商目录、粘贴 Key、按任务选模型、切六项能力实现——写入走「校验 → 落库
`app_settings` → 同步进程内配置 → 清能力工厂缓存」这一条写穿链路，**不需要重启**；回读只给掩码；
未在设置页改过的项一律回落 `.env` 引导默认。

**分支 / commit**：`JulianZBY/issue-13-settings`。代码与测试所在的提交对象 = `be9b145`
（用 `git show be9b145 --stat` 核对，24 个文件）；其后一个同信息提交只补本交付记录与验收勾选。
基线 `bb61726`。未 push、未开 PR、未 merge/rebase。

### 新增文件

| 文件 | 职责 |
| --- | --- |
| `backend/app/core/catalog.py` | 供应商目录 + 可选能力实现 + 任务清单 + 目录口径校验（字段与取值口径的唯一出处） |
| `backend/app/core/settings_store.py` | 设置库：读 / 写 / 生效同步；**统一的缓存失效入口** `invalidate_capabilities()` |
| `backend/app/core/llm/task_routing.py` | 任务级模型：`model_for()`（实际用的模型 + 来源）、`get_llm_for(task)` |
| `backend/app/api/v1/settings.py` | 三个端点（读取 / 写入 / 可选目录）+ 启动同步钩子 + OpenAPI 注解 |
| `backend/tests/test_settings_api.py` | 24 个用例（HTTP 缝 + 能力工厂缝） |
| `frontend/src/areas/settings/OptionPicker.tsx` | 设置页的下拉选择器（Radix DropdownMenu 皮肤，键盘 / Esc 由原语承担） |

### 改动文件（要点）

- `app/db/models.py`：**末尾追加** `AppSetting`（key / value / updated_at，字段带中文语义注释）
- `app/config.py`：追加 `task_model_intent` / `task_model_generate` / `task_model_conflict`（留空 = 回落全局默认）
- `app/api/v1/router.py`：**只追加**一行 import + 一行 `include_router`
- `app/core/llm/factory.py`：新增 `custom` 构造器（自定义 OpenAI 兼容服务：base_url + 模型 ID + Key）
- 8 个模块按任务取档位（10 处 `get_llm()` 调用共享本模块的档位绑定；见下方「越界披露」第 2 条）
- `app/main.py`：`TAGS_METADATA` 追加「设置」分组（见下方「越界披露」第 1 条）
- `frontend/src/areas/settings/{queries.ts,SettingsArea.tsx}`：读写接线 + 四张卡（供应商目录 / 任务级模型 /
  能力实现 / 自定义 OpenAI 兼容服务）
- `frontend/openapi/openapi.json`、`frontend/src/api/generated/*`：`npm run gen:api` 重新生成
- `backend/.env.example`：末尾追加 TASK_MODEL_* 与「设置库优先于本文件」的说明

### 验收证据

#### 证据 1：目录选择 + 填 Key 后无重启即生效（真进程实测）

用例：`test_provider_switch_with_key_becomes_ready_without_restart`（读回来的供应商 / Key 掩码 / ready）、
`test_capability_switch_takes_effect_without_restart`（写成 `vector` 后既有检索端点当场返回 `strategy=vector`）、
`test_capability_switch_changes_the_factory_immediately`（PDF / 语音转写 / 搜索三档的工厂当场换实现类）。

实测（`uvicorn` 真进程 + 临时库 `data/tmp-settings-demo.db`，验证完已删）：

```text
起点供应商 = stub / ready=True / 来源=引导默认
写后供应商 = deepseek / label=DeepSeek / ready=True / 来源=设置页
写后 Key 掩码 = ••••1234
响应里是否含明文 = False
全局默认模型(生效) = deepseek-chat
检索策略：起点=vector_graph -> 写后端点返回 strategy=vector
无效配置 -> HTTP 400: {"detail":{"code":"unknown_capability_impl","field":"asr_provider",
  "message":"未实现的语音转写：whisper（可选：stub、paraformer）"}}
```

#### 证据 2：重启后仍是设置库说了算（配置库 > `.env` 引导默认）

用例：`test_stored_settings_survive_a_restart`（进程内配置先回到引导默认，再由启动钩子重放设置库）。
实测：另起一个 `uvicorn` 进程、连同一个库：

```text
重启后供应商 = deepseek / ready=True / 来源=设置页
重启后 Key 掩码 = ••••1234
重启后检索策略 = vector
重启后任务级模型: 意图分析=deepseek-chat[全局默认] / 生成=deepseek-reasoner[任务级] / 冲突比对=deepseek-chat[全局默认]
```

#### 证据 3：任务级模型与回落全局默认的行为可见

- 页面上可见：`tasks[]` 逐任务给 `selected` / `model`（该任务实际用的）/ `source`（任务级 / 全局默认）——
  用例 `test_task_models_fall_back_to_the_global_default`。
- 真的进了调用：用例 `test_task_level_models_reach_each_call_site` 把对话能力替身挂进能力注册表，
  依次跑「意图分析 → 生成 → 冲突比对」三条链，断言每次对话带上的模型依次是
  `["intent-model", "generate-model", "conflict-model"]`；清空任务档位后变成 `[None]`（由全局默认承担）。

#### 证据 4：Key 全程掩码

用例 `test_key_is_masked_in_every_response`：对 PUT 与 GET 的**原始响应体**断言不含明文
（`PLAINTEXT not in response.text`），且掩码为 `••••9a41`；库内保存的是原文（要拿去调用）。
`test_short_key_is_masked_completely`：短 Key 连尾部都不给（`••••`）。
`.env.example` 与 OpenAPI 示例里的 Key 一律是占位文案或掩码，截图 / 文档不会带出真 Key。

#### 证据 5：无效配置返回明确错误码与信息

用例 `test_invalid_config_returns_explicit_error_code`（参数化 6 组）
+ `test_invalid_write_leaves_earlier_settings_untouched`：

| 输入 | 400 的 `code` | `field` |
| --- | --- | --- |
| `llm_provider=openai-x` | `unknown_provider` | `llm_provider` |
| `llm_provider=dashscope, llm_model=gpt-4o` | `unknown_model` | `llm_model` |
| `task_model_generate=没有这个模型` | `unknown_model` | `task_model_generate` |
| `asr_provider=whisper` | `unknown_capability_impl` | `asr_provider` |
| `llm_base_url=example.com/v1` | `invalid_base_url` | `llm_base_url` |
| `embedding_base_url=ftp://example.com/v1` | `invalid_base_url` | `embedding_base_url` |

每组都断言「库内一行不动 / 既有设置不变」。`message` 直接给教师看，并指路「目录之外的模型请用
自定义 OpenAI 兼容服务」。

#### 证据 6：前端过风格文档第 7 节清单（自检结论）

单页表单、编辑密度（`max-w-xl` 单列窄容器，大留白，一次只做一件事）；容器一律 `Card`（`border-2
border-black` + `rounded-none`）；只有黑 / 白 / `#ff3366`（强调色上只放黑字，标记用直角方块不写文字）；
无阴影 / 无渐变 / 无灰底 / 无半透明底；悬停黑白反色（输入框按例外走边线加粗）、聚焦 `outline` 可见、
禁用降级由组件库承担；过渡只 `transition-colors duration-150`；加载态 = 直角方块 `animate-spin` + 文案；
无 emoji；弹层用 Radix（键盘 / Esc 可关）。禁用 class 扫描：58 个文件、10 条规则零违规。

### 跑过的命令与结果

```text
cd backend && uv run pytest -q        → 244 passed（既有 220 + 本票 24）
cd backend && uv run ruff check .     → All checks passed!
cd frontend && npm run lint           → check:classes 58 文件零违规 + oxlint 无告警
cd frontend && npm run build          → 禁用 class 扫描 + tsc -b + vite build 通过
cd frontend && npm run check:routes   → 七条路由可达（含 /settings 渲染出「供应商目录」）
cd frontend && npm run gen:api        → OpenAPI 快照 + TS 类型重新生成
```

### 越界披露（三处）

1. **`backend/app/main.py`：`TAGS_METADATA` 追加「设置」分组（7 行）**。已向协调者报备并放行；只有
   `main.py` 能声明 tag 描述，不追加则 `test_openapi_contract.py` 的「用了未声明的 tag」与「声明的 tag
   空置」两组断言必红。
2. **任务级模型的调用点**：`app/core/intent.py`、`app/generate/{outline,word,ppt,exam,revise,creative}.py`、
   `app/knowledge/conflict.py`。协调者给的形态是「一行 `get_llm()` → `get_llm_for("generate")`」；
   实际形态是**保留模块内的 `get_llm` 名字、把它绑成任务档位**：
   `get_llm = partial(get_llm_for, "generate")` + 两行注释（每文件 2 行，`revise.py` 两个调用点共享一个绑定）。
   理由：既有 8 个测试文件里有 22 处 `monkeypatch.setattr(模块, "get_llm", ...)` 接缝（票 02/03/05/06 留的），
   改名会把它们一起拖进来改——改动面反而更大，且会与并行票的测试文件相撞。行为与「一行替换」完全一致：
   这些模块的 `get_llm()` 现在按任务取档位，未设置回落全局默认。
3. **`backend/.env.example`：末尾追加任务级模型三行 + 设置库优先级说明**（票 03 有同样先例；新增的
   `TASK_MODEL_*` 需要一处可发现的引导默认说明）。

另外两处不属越界但要说明：

- `app/core/intent.py` 的 `intent_from_payload` 把兜底句式从 `str(payload.get("topic") or "")` 改成
  先把 `topic` 取出来再 `str(topic)`：pi-lens 的 `ast-grep:no-boolean-in-except` 规则会把 `except` 子句
  **体**里的 `or` 当违规命中（`stopBy: end`，误报），行为完全等价。
- `frontend/openapi/openapi.json` 重刷带出 2000+ 行变化：该快照此前已过期（缺票 03 的
  `/knowledge/retrieve` 与票 05 的 `/sessions` 三个端点），`npm run gen:api` 顺手补回；不重刷则本票的新
  类型无从生成。

### 两轴自审

- **Standards**：分层——`api/v1/settings.py` 只做装配与 OpenAPI 注解，目录口径与校验住
  `core/catalog.py`，写穿与缓存失效住 `core/settings_store.py`，新表只追加在 `db/models.py` 末尾；
  能力选择仍走注册表（可选实现 = 注册表键，注册表加一行设置页就多一个选项）；OpenAPI 纪律——3 个新端点
  全带 summary / 描述 / 请求与响应示例 / 错误码 / 「设置」tag，且**都带 `response_model`**
  （另加守卫用例 `test_settings_operations_all_declare_a_response_model` 防回退，正是票 04 指出的坑）；
  面向教师的文案用 CONTEXT.md 第 8 节术语（供应商目录 / 自定义 OpenAI 兼容服务 / 任务级模型 / 引导默认 /
  掩码 / stub 模式）；测试只断 HTTP 响应、库内数据变迁与工厂产物，不 mock 被测对象。
- **Spec**：8 项 What to build 与 6 条验收逐条落地（见上）；「写穿 = 写库 + 清缓存」的**统一失效入口**
  `invalidate_capabilities()` 是本票对票 03 遗留的收口（调用点不再各自 `cache_clear`）；
  既有端点路径与既有字段语义未动（`/settings` 是全新路径）。

### 遗留 / 注意事项

1. 设置写穿是「最后一次写入为准」：单用户本地应用不做并发加锁，两个浏览器同时保存同一项会互相覆盖。
2. Key 以原文存在本地 SQLite（要拿去调用云端），只在回读时掩码；本地库的访问控制不在本票范围（单用户、无登录）。
3. 模型档位只在「对话供应商目录 + 自定义服务」口径下校验：向量化模型视为自由文本（`EMBEDDING_PROVIDER=openai`
   本就是任意模型 ID），所以 `unknown_model` 不会拦向量化模型名。
4. 切换向量化口径后，库里的向量与新口径不一致，需要重建向量库再检索（页面上有一行提示，自动重建不在本票范围）。
5. `frontend/src/components/ui/index.ts` 未改：`OptionPicker` 是本区文件、按区目录规范直接 import，
   避免与并行票争同一个导出文件。
6. stub 模式下没有模型档位（`model` 是空字符串），页面按「尚未确定 / 未设置」显示——不是缺数据，
   是 stub 本就不区分模型。
7. 设置接口没有「测试连接」按钮：探测需要真发一次请求，本票只做离线的就绪探针（缺 Key 时读接口直接
   说明原因）。

### 补丁：用例对开发者 `.env` 的依赖（合入后修复，2026-09-24）

**症状**：在带真 Key 的 `backend/.env` 的仓库里，合入本票后两条用例红——
`test_read_starts_from_bootstrap_defaults`（`all(not key["configured"] and key["masked"] == "")` 为 False）
与 `test_empty_value_clears_the_item_back_to_bootstrap`（清空后仍 `configured=true`）。

**根因**：用例假设「设置库为空 ⇒ 所有 Key 都未配置」，但引导默认是 `.env` 的**进程启动快照**
（`app/core/settings_store.py` 的 `_BOOTSTRAP`），而按设计「配置库优先于 `.env` 引导默认」——
`.env` 里有真 Key 时那把 Key 本身就是引导默认，读回来自然 `configured=true`。
**产品行为正确，是用例对环境的假设错了**（本票原工作树没有 `.env`，所以没暴露）。

**复现**（假 Key 写进 `backend/.env`，该文件在 `.gitignore` 内，未入库）：

```text
backend/.env（gitignored）
  DASHSCOPE_API_KEY=sk-test-dashscope
  DEEPSEEK_API_KEY=sk-test-deepseek
  SILICONFLOW_API_KEY=sk-test-siliconflow
  MINERU_TOKEN=test-token
  BOCHA_API_KEY=test-bocha

$ cd backend && uv run pytest -q tests/test_settings_api.py
FAILED tests/test_settings_api.py::test_read_starts_from_bootstrap_defaults
FAILED tests/test_settings_api.py::test_empty_value_clears_the_item_back_to_bootstrap
2 failed, 22 passed

$ uv run pytest -q          # 全量同样只有这两条红
2 failed, 242 passed
```

**改动**（只改 `backend/tests/test_settings_api.py`，产品代码一行未动）：

- 新增 autouse 夹具 `_isolated_bootstrap_defaults`：把 `settings_store._BOOTSTRAP` 换成
  **`Settings` 的代码默认值**（无 `.env`、无环境变量；22 个可改项：`llm_provider=stub`、Key 全空、
  `pdf_strategy=mineru_then_pypdf`、`retrieval_strategy=vector_graph`、任务级档位全空……），
  随后 `apply_stored_settings()` 让进程内配置一并回落；用例结束 `monkeypatch.undo()` 把真值快照放回
  并再重放一次，不把受控值留给后面的测试文件。
- 既有夹具 `_clean_settings_store` 改为依赖它：清理用的是受控引导默认，且两个夹具按「先建后拆」
  归还真值。泄漏另用临时探针验证：在本文件之后紧接断言
  `settings_store.bootstrap_value("dashscope_api_key") == <本机 .env 的值>` 通过（探针跑完即删）。
- 断言文本一个字未改（「设置库为空 ⇒ Key 未配置」在受控引导默认下成立），只把前提钉住；
  相关 docstring / 注释说明「引导默认由夹具控制成无 `.env` 的口径」。
- 为什么控制**全部**可改项而不只 Key：同一类假设还有「默认检索策略 / 默认供应商」（见下方范围外发现），
  一次封掉整类缺陷。为什么留在本文件而不进 `conftest.py`：目前只有本文件做这类断言，
  不动全量测试的环境口径（越界成本高于收益）。

**验收（两个方向都过）**：

```text
方向 A：backend/.env 存在（五条假 Key）
$ uv run pytest -q tests/test_settings_api.py   → 24 passed
$ uv run pytest -q                              → 244 passed
$ uv run ruff check .                           → All checks passed!

方向 B：backend/.env 改名后（等价于删掉）
$ uv run pytest -q tests/test_settings_api.py   → 24 passed
$ uv run pytest -q                              → 244 passed
```

额外一轮：把 `.env` 改写成「偏离代码默认」的口径（`LLM_PROVIDER=deepseek`、`SEARCH_PROVIDER=bocha`、
`ASR_PROVIDER=paraformer`、`PDF_STRATEGY=pypdf`、`RETRIEVAL_STRATEGY=vector`、`EMBEDDING_PROVIDER=hash`、
`TASK_MODEL_INTENT=deepseek-reasoner`），本文件仍 24 passed；验证完已把 `.env` 还原成任务给的那五条假 Key。

**范围外发现（未改，供分派）**：

1. 同一类环境依赖还在别的测试文件里：上面那一轮「偏离代码默认的 `.env`」下
   `tests/test_rag_strategies.py::test_default_retrieval_matches_pre_refactor_golden`（`assert retriever.name == "vector_graph"`）、
   `tests/test_rag_strategies.py::test_retrieve_endpoint_reports_what_was_hit`、
   `tests/test_graph_retrieval.py::test_adjacent_node_content_reaches_llm_gateway`、
   `tests/test_graph_retrieval.py::test_context_respects_budget_chunks_first_nodes_truncated` 红——
   它们断言「默认档」时同样假设 `.env` 未覆盖 `RETRIEVAL_STRATEGY` 等项。本单边界只到
   `test_settings_api.py`，故只报告不修。（只带 Key 的真实 `.env` 碰不到它们，所以这次合入只暴露了本票这两条。）
2. `app/api/v1/settings.py` 里 `_capabilities()` **定义了两次**（287 行与 306 行，函数体一模一样）：
   产品代码的重复定义（ruff 默认规则不报），行为无影响，但应删一处；不在本单边界内。

本票 `Status` 未动（仍是文件里的原值），验收勾选也未改。

## 协调者复核

**结论：通过（含一次由协调者发现缺陷后触发的收尾补丁）。** 复核人 = 协调者（主代理），2026-09-24。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| 目录选择 + 填 Key 后无重启即生效 | `app/core/settings_store.py` 的写穿 + `invalidate_capabilities()`；交付记录有真进程实测 | 通过 |
| 任务级模型与回落全局默认行为可见 | `app/core/llm/task_routing.py` + 8 个模块按任务取模型（协调者放行的最小调用点替换） | 通过 |
| 自定义 OpenAI 兼容接入 | 目录外的 `base_url` + 模型 ID | 通过 |
| Key 全程掩码 | 交付记录含「PUT/GET 原始响应体无明文」断言 | 通过 |
| 无效配置返回明确错误码 | `unknown_provider` / `unknown_model` / `unknown_capability_impl` / `invalid_base_url`，400 | 通过 |
| 能力切换即时生效 | 检索策略改成 `vector` 后紧接着的检索请求即返回 `strategy=vector` | 通过 |
| 测试与静态检查 | 协调者亲跑 244 passed、`ruff check .` 干净 | 通过（修复前） |

**协调者放行的两处越界（已按用户裁决）**：① `main.py` 追加「设置」tag（与票 12 的「题库」同法）；② 7 处「任务档位」最小调用点替换——协调者判定「只留 seam 等于功能未实现」，故放行并要求只改那一行。

**协调者发现的缺陷 → 同工作树续派修复**：合入主干后，`tests/test_settings_api.py::test_read_starts_from_bootstrap_defaults` 在**带真实 `.env` 的仓库**里失败。甄别结论：**产品行为正确，是用例假设了「`.env` 为空」**（引导默认里有 Key 本就该显示为已配置）。续派（新终端 + 既有工作树，因 Orca runtime 期间重启过）后交付 `f8aee68`：新增 autouse 夹具把引导默认钉成「本机无 `.env`」的代码默认，**产品代码一行未动**；带假 Key `.env` 与改名后**两个方向都全绿**。协调者在真实 `.env` 存在的 main 上复验：该文件 **24 passed / 3 秒**。

- **合并点**：`df4e8eb`（`merge(13)`）+ `1d4f67a`（密封性补丁）。
- **状态迁移**：`ready-for-agent` → `done`。
- **遗留去向（均登记进票 14）**：① 同类环境依赖仍在 `test_rag_strategies.py`（2 条）与 `test_graph_retrieval.py`（2 条）；② `app/api/v1/settings.py` 的 `_capabilities()` 重复定义两处；③ 写穿无并发加锁、Key 原文入库、无「测试连接」按钮。
