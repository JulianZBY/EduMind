# 14: 端到端验收收口

**What to build:** 重构收口：stub 模式全链路冒烟（上传 → 备课对话 → 生成物 → 下载 → 冲突审核），风格自检清单全过、禁用类扫描零违规，主干任一时刻可跑，规格 36 条用户故事逐条核对；README、架构一页图、接口专题与现实一致。

**Blocked by:** 01–13 全部 + 15 视觉提取的 stub

**Status:** done

- [x] stub 模式从文档上传到备课对话到生成物下载全流程走通，且**图片/视频上传在 stub 模式下不再必然失败**（依赖票 15）
- [x] 风格自检清单逐项通过，禁用类扫描零违规
      【口径】禁用 class 10 条规则与 lint / build **零违规（机器可判部分全部通过）**；
      「悬停反色 / 四态 / 密度 / mermaid 扁平主题」这类**只能人眼看**的项本机无浏览器，
      已逐项写进本票新建的 `docs/acceptance-manual.md` 第 3 节（可照做勾选），不假装已验过。
- [x] 规格 36 条用户故事逐条可演示或可解释
- [x] README、架构一页图、接口专题与现实一致
- [x] 后端测试全绿，主干按 README 步骤可跑
- [x] **测试套件不密封（2026-09-24 协调者实测发现，本票收口）**：测试结果受开发者 `backend/.env` 影响——main 工作树有 `.env`（`LLM_PROVIDER=dashscope` + 真实 Key）时，全量测试跑 13.5 分钟并在 `tests/test_artifact_versions.py` 出现 3 条假失败（断言的是 stub 固定产出）；把 `LLM_PROVIDER=stub` 后同样代码 **274 passed / 13 秒**。要求在 `tests/conftest.py` 用 `os.environ.setdefault` 钉住 stub 类配置（至少 `LLM_PROVIDER` / `EMBEDDING_PROVIDER`，按需含 `SEARCH_PROVIDER` / `PDF_STRATEGY`），使测试不依赖任何真实 Key 与网络；验收方式：**把 `backend/.env` 里的 provider 设为真实值（或直接拷一份 `.env`）后全量跑，仍必须全绿且耗时稳定**。
- [x] **补齐既有操作的 `response_model`（票 04 报告的缺口，本票收口）**：票 04 指出 6/16 操作缺 `response_model`，导致前端生成类型是 `unknown`；新增端点已由各票自带，**历史缺口在此补齐**，补完重跑 `npm run gen:api` 并确认前端类型不再是 `unknown`。

### 协调者本轮追加（2026-09-24，本票必须照做）

- [x] **测试密封性**：conftest 钉住 stub 档；敌意 `.env` 与无 `.env` 两个方向全量测试都全绿，并给出耗时对比。
- [x] **补齐 4 个回 JSON 端点缺的 `response_model`**：`GET /health`、`GET /api/v1/ping`、`GET /`、`POST /api/v1/knowledge/web-search`；补完盘点只剩 2 个文件下载端点（正当例外）。

## 交付记录

**分支**：`JulianZBY/issue-14-e2e-acceptance`（本工作树当前分支；未 push / 未开 PR / 未 merge / 未 rebase）
**基线**：起点 `3a2007a`（`merge(08)`）；`main` 仅比它多一个**纯登记提交** `d621cfd`（`chore(tracker): 08 复核 done`，只改 08 的票文件，无代码差异），因此本工作树的代码与主干一致。
**提交**：本分支 tip `chore(14): 端到端验收收口`（代码 + 测试 + 文档 + 本记录；单提交，工作树干净）。

### 一、跑过的命令与结果

| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm install` / `cd backend && uv sync` | 成功（全新工作树） |
| `cd backend && uv run pytest -q`（**无 `.env`**） | **334 passed**，17.7s |
| `cd backend && uv run pytest -q`（**敌意 `.env` 在位**） | **334 passed**，16.6s |
| 同上两方向但用**未密封**的旧 conftest（对照） | **37 failed / 297 passed**，31.8s；失败集中在 7 个文件（见第二节） |
| `uv run pytest tests/test_rag_strategies.py tests/test_graph_retrieval.py -q`（未密封 + 敌意） | **4 failed**（正是票 13 报告的那 4 条）→ 密封后 **19 passed** |
| `uv run ruff check .` | `All checks passed!` |
| `cd frontend && npm run lint` | `[check:classes] 104 个文件，10 条规则零违规` + oxlint 通过 |
| `cd frontend && npm run build` | 通过（tsc -b + vite build） |
| `cd frontend && npm run check:routes` | 七条路由全部可达，默认路由 = 备课会话 |
| `cd frontend && npm run gen:api` | 33 条路径 / 37 个操作；TS 类型重新生成 |
| 响应模型盘点（脚本见第五节） | 改动前 **6 个**回 JSON 的端点无 schema；改动后**只剩 2 个文件下载端点**（正当例外） |
| stub 全链路冒烟（真 uvicorn :8099 + 真 HTTP，无任何 Key） | **25 步全过**（第四节） |
| README 启动步骤实测（uvicorn :8000 + `npm run dev` :5173） | `/health` = `llm_provider=stub`；`http://localhost:5173/` = 200；经 vite 代理的 `/api/v1/ping` = 200 |
| 落盘隔离核对 | **测试**：数据全在临时目录（conftest 钉 `DATABASE_URL` / `VECTORS_DB_PATH` / `UPLOAD_DIR`），`backend/data` 一次都没被测试写；**冒烟与 README 启动实测**：按应用默认行为写了 `backend/data/output` 与 `backend/edumind.db`（都在 `.gitignore` 内，不在提交里），验收后已删除，工作树干净 |
| `git status --short` | 只有本票改动（代码 + 测试 + 文档 + 票文件），无残留与临时脚本 |

### 二、验收项：测试套件不密封 → 已密封

**改法**（`backend/tests/conftest.py`，在任何 app 模块导入前）：

- 用 `os.environ.setdefault` 钉住 **7 项能力配置**：`LLM_PROVIDER=stub`、`EMBEDDING_PROVIDER=stub`、`ASR_PROVIDER=stub`、
  `SEARCH_PROVIDER=stub`、`RETRIEVAL_STRATEGY=vector_graph`、`CHUNK_STRATEGY=paragraph`；
  并把 5 个云端 Key（`DASHSCOPE/DEEPSEEK/SILICONFLOW/MINERU/BOCHA` + `LLM_API_KEY`/`EMBEDDING_API_KEY`）钉为空字符串作双保险。
- **没有**钉 `PDF_STRATEGY`：其代码默认 `mineru_then_pypdf` 是既有测试断言的一部分（`tests/test_settings_api.py` 断言起点是 `FallbackPdfParser`），
  改钉它会造成另一种「测试依赖环境」；不缺 token 时它本来就走 pypdf，而 `MINERU_TOKEN` 已被钉空，因此不会走网络。
- 环境变量优先级高于 `.env`，所以 `setdefault` 能压住开发者 `.env`；显式在 shell 设了值的仍以 shell 为准（想在真 provider 上跑一次仍可以）。

**验收方式一：敌意 `.env`**（不入库，验收后已删）——值与代码默认全部相反，Key 全是假的：

```ini
LLM_PROVIDER=deepseek
EMBEDDING_PROVIDER=deepseek
ASR_PROVIDER=paraformer
SEARCH_PROVIDER=bocha
PDF_STRATEGY=mineru
RETRIEVAL_STRATEGY=vector
CHUNK_STRATEGY=paragraph
DASHSCOPE_API_KEY=sk-evil-dashscope-0001
DEEPSEEK_API_KEY=sk-evil-deepseek-0002
SILICONFLOW_API_KEY=sk-evil-siliconflow-0003
MINERU_TOKEN=evil-mineru-token-0004
BOCHA_API_KEY=sk-evil-bocha-0005
```

**验收方式二：无 `.env`**。两个方向都 **334 passed**。

**耗时对比**（同一台机器、同一代码）：

| 场景 | 结果 | 耗时 |
| --- | --- | --- |
| 密封后 + 敌意 `.env` | 334 passed | 16.6s |
| 密封后 + 无 `.env` | 334 passed | 17.7s |
| **未密封** + 敌意 `.env`（对照） | 37 failed / 297 passed | 31.8s |
| 未密封 + 真 provider（协调者实测，见票面） | 3 条假失败 | 13.5 分钟 |

**红 → 绿的直接证据**（票 13 报告的 4 条）：

```text
# 未密封 conftest + 敌意 .env
FAILED tests/test_rag_strategies.py::test_default_retrieval_matches_pre_refactor_golden
FAILED tests/test_rag_strategies.py::test_retrieve_endpoint_reports_what_was_hit
FAILED tests/test_graph_retrieval.py::test_context_respects_budget_chunks_first_nodes_truncated
FAILED tests/test_graph_retrieval.py::test_adjacent_node_content_reaches_llm_gateway
4 failed, 15 passed in 2.88s
# 密封 conftest + 同一个敌意 .env
19 passed in 2.16s
```

**对照全量跑**发现假失败比票 13 报告的更多（37 条，集中在 7 个文件）：

| 文件 | 假失败条数 |
| --- | --- |
| `tests/test_artifact_versions.py` | 15 |
| `tests/test_conflict_categories.py` | 8 |
| `tests/test_artifact_revision_paths.py` | 5 |
| `tests/test_vision_stub.py` | 3 |
| `tests/test_documents_workbench.py` | 2 |
| `tests/test_graph_retrieval.py` | 2 |
| `tests/test_rag_strategies.py` | 2 |

这印证了「不密封 = 本机绿、换机器红」：开发者 `.env` 一换，十多条用例的结论就变了。密封后两个方向完全一致。

### 三、验收项：补齐 4 个 `response_model`

盘点脚本（输出见第五节）改动前后：

```text
# 改动前（backend/ 下，PYTHONPATH=. uv run python <盘点脚本>）
total operations: 37
JSON 200 responses without schema: 6
  GET    /health                          -> {}          ← 本票补齐
  GET    /api/v1/artifacts/{version_id}/download -> {}   ← 正当例外（文件流）
  GET    /api/v1/files/{filename}         -> {}          ← 正当例外（文件流）
  POST   /api/v1/knowledge/web-search     -> {}          ← 本票补齐
  GET    /api/v1/ping                     -> {}          ← 本票补齐
  GET    /                                -> {}          ← 本票补齐

# 改动后
JSON 200 responses without schema: 2
  GET    /api/v1/artifacts/{version_id}/download -> {}   ← 正当例外（application/octet-stream）
  GET    /api/v1/files/{filename}         -> {}          ← 正当例外（application/octet-stream）
```

- 新增 4 个模型：`HealthResponse`（`api/health.py`）、`RootResponse`（`main.py`）、`PingResponse`（`api/v1/router.py`）、
  `WebSearchResponse` + `WebSearchResult`（`api/v1/knowledge.py`），全部带字段语义注释与 `json_schema_extra` 示例；
  原有 200 响应示例注解保留（FastAPI 会把 `$ref` 合并进同一条 200，示例不丢）。
- **新增回归守卫**：`tests/test_openapi_contract.py::test_json_endpoints_declare_a_response_model`——
  以后任何回 JSON 的新端点忘了 `response_model` 都会被这条挡住（文件流两个端点显式列为例外）。
- 重跑 `npm run gen:api`：前端类型里这 4 个端点不再是 `unknown`（`PingResponse` / `WebSearchResponse` / `RootResponse` / `HealthResponse`）；
  `frontend/src/api/system.ts` 顺手把 `apiRequest<unknown>` 换成生成的 `PingApiV1PingGetResponse`（`/health` 已有 schema 的旧注释一并改掉）。
- 未重复处理 `/documents` 两个端点（票 09 已补 `DocumentView` / `DocumentListResponse`），也未给两个下载端点强加模型。

### 四、验收项：stub 模式全链路冒烟（真服务 + 真 HTTP）

跑法（与 `docs/acceptance-manual.md` 附录 A 同源，脚本本票未入库，按附录 A 的命令可复现）：
临时库 / 临时向量库 / 临时上传目录 + 不配任何 Key，`uv run uvicorn app.main:app --port 8099`，再用 `curl.exe` 与 `Invoke-RestMethod` 打 HTTP。素材由脚本现场造：真 PDF（手写最小 PDF，含文本层）、真 PNG、真 MJPG/AVI（各 8 帧）、真 `.docx`。

```text
[OK] 服务起来（GET /health） — llm_provider=stub status=ok app=EduMind
[OK] stub 模式确认（无云端 Key） — llm_provider=stub
[OK] 上传 PDF 立即返回处理中 — status=处理中 file_type=pdf
[OK] PDF 走到终态已完成 — status=已完成 chunk_count=1 parsed_at=…
[OK] 图片走到终态已完成（stub 视觉） — chunks=1 标记命中=True
[OK] 视频走到终态已完成（抽帧 + stub 视觉） — chunks=1 帧标记=True
[OK] 上传 Word 资料走到终态已完成 — status=已完成 chunk_count=1
[OK] 新建备课会话并勾选参考资料 — reference_doc_ids=<pdf id>
[OK] stub 下第一轮直接出生成回复（澄清分支在 stub 下不可达） — clarifying=False
[OK] 第二轮对话（信息够用时是生成回复） — 已完成备课「TCP 三次握手」：生成 PPT 5 页、Word 教案、教学提纲
[OK] 生成回复带上命中的参考资料来源（溯源） — references=tcp-terms.docx,tcp-handout.pdf,whiteboard.png,clip.avi
[OK] 版本中心列出本次生成的各版生成物 — 版本数=6 分组=课件/教案/提纲
[OK] 版本详情可取回（含内容与下载地址） — label=第 2 版 content 键=slides
[OK] 任意版本可下载（课件 .pptx 字节流） — HTTP=200 bytes=32873
[OK] 以历史版本为基线修改 → 产出更高版本号的新版本 — 基线版本=2 新版本=3 origin=修改 总版本数=6→7
[OK] 一键生成试卷并自动入题库 — 题目数=3 bank_saved=3
[OK] 题库可浏览（题目带考查知识点） — 带知识点标注=3 首题「TCP滑动窗口(主考)」
[OK] 题库按考查知识点筛选可取回 — 筛选后题目数=1
[OK] 互动内容生成 + 新标签页内联打开（inline 下载） — HTTP=200 首行=<!DOCTYPE html>
[OK] 知识图谱渲染数据可取回（节点 + 关系） — 节点数=8 关系数=4
[OK] 冲突队列按三类别列出待审 — 待审数=3 类别=常识存疑,定义冲突,结构冲突
[OK] 结构冲突带「图谱现状 vs 三种裁决终态」图示 — 终态动作=接受新/保留旧/并存
[OK] 定义冲突三选一（接受新）生效 — status=已接受
[OK] 常识存疑编辑修正后入库生效 — status=已接受
[OK] 裁决后队列只剩未裁决的那条 — 剩余待审=1
汇总：25 步，通过 25，失败 0
```

**两条必须写清楚的口径**（不是缺陷，是 stub 的边界，已写进 `docs/api/stub-mode.md`）：

1. **澄清回复在 stub 下走不到**：stub 的意图分析返回**固定且要素齐全**的意图，`missing_fields` 恒为空，
   所以每一轮都是生成回复——追问粒度与「跳过追问」判定不参与。澄清分支的自动化证据是 HTTP 缝用例
   `uv run pytest tests/test_chat.py tests/test_session_turns.py -q`（**14 passed**，用意图替身注入不完整意图），
   真浏览器演示留给人工清单（真实 Key）。
2. **冲突在 stub 下不会自然出现**：stub 的比对恒返回 `{"conflict": false}`，且结构冲突 / 常识存疑的检测
   **尚未实现**（ADR-0006）。冒烟里的三条待审是**直接种进临时库**的种子数据，用来验证三类别形态与差异化动作。

### 五、响应模型盘点脚本（可复现）

在 `backend/` 下（`PYTHONPATH=. uv run python <脚本>`），判据：200 响应含 `application/json` 且 schema 里
没有任何 `$ref`/`allOf`/`items`/`properties` 等结构描述（只有 `example` 不算）。

```python
import json
from app.main import app

METHODS = ("get", "post", "put", "patch", "delete")
HINT_KEYS = ("$ref", "allOf", "items", "properties", "oneOf", "anyOf", "additionalProperties")

schema = app.openapi()
total, missing = 0, []
for path, ops in schema["paths"].items():
    for method, op in ops.items():
        if method not in METHODS:
            continue
        total += 1
        content = op.get("responses", {}).get("200", {}).get("content", {})
        if "application/json" not in content:
            continue
        sub = content["application/json"].get("schema", {})
        if any(k in sub for k in HINT_KEYS):
            continue
        missing.append(f"{method.upper():6s} {path:52s} -> {json.dumps(sub, ensure_ascii=False)}")
print(f"total operations: {total}")
print(f"JSON 200 responses without schema: {len(missing)}")
for row in missing:
    print("  " + row)
```

### 六、用户故事逐条核对（36 条）

判定口径：**可演示** = 本票已跑通或已有点选/命令证据；**可解释** = 实现存在但本机（无 Key / 无浏览器）看不到，
已写清「谁能看到、怎么看到」；**未实现** = 照实写并给原因。要人做的那几件集中在 `docs/acceptance-manual.md`。

| # | 用户故事 | 判定 | 证据 / 说明 |
| --- | --- | --- | --- |
| 1 | 会话为中心的工作台发起备课对话 | 可演示 | 冒烟 8–10（`POST /sessions` + `POST /chat`）；界面 `/lesson-prep` 为默认落脚区（`check:routes`） |
| 2 | 发起会话时勾选参考资料 | 可演示 | 冒烟 8（`reference_doc_ids`）+ 回复里的 `references`（冒烟 11） |
| 3 | 会话内直接上传文件并自动归入参考资料 | 可演示 | 前端 `useAttachReference`：上传带 `is_reference=true` + `PATCH /sessions/{id}` 绑定；真浏览器点选见人工清单 1.1 |
| 4 | 调整追问粒度（快速/标准/精细） | **可解释** | 粒度→必需字段的映射在 `core/clarify.py`，三档都有 HTTP 缝用例（`test_session_turns.py`）；**stub 下走不到**（意图固定完整），真 Key 下看人工清单 2.3 |
| 5 | 「开始生成」跳过追问 | **可解释** | 按语义判定（`core/clarify.py` `SKIP_JUDGEMENT_MARKER`，非关键词），替身用例覆盖；stub 恒返回 `skip=false`，故 stub 下看不到 |
| 6 | 多台设备看到同一份会话列表 | 可演示 | 会话/消息/意图全部落库（`GET /sessions`）；人工清单 1.1「换浏览器」 |
| 7 | 清掉浏览器数据后历史仍在 | 可演示 | 同上（无 localStorage 事实源） |
| 8 | 检索 / 重命名 / 删除会话 | 可演示 | `GET /sessions?keyword=`、`PATCH`、`DELETE`（`test_sessions_api.py`） |
| 9 | 生成后在对话旁并排看到课件/教案/提纲 | 可演示 | `lesson-prep/GenerationPreview.tsx` 挂在对话轴旁；数据来自同一个版本查询（冒烟 13） |
| 10 | 对单个生成物提修改意见再生成 | 可演示 | 冒烟 15（`/revise/outline`）；课件/教案另有 `/revise`、`/revise/word` |
| 11 | 查看某次会话的全部历史版本 | 可演示 | 冒烟 13（6 个版本，分组 课件/教案/提纲） |
| 12 | 下载任意历史版本 | 可演示 | 冒烟 14（HTTP 200，32873 字节） |
| 13 | 以历史版本为基线继续修改 | 可演示 | 冒烟 15（基线=第 2 版 → 新第 3 版，旧版仍在） |
| 14 | 一键生成试卷且题目入题库并标注考查知识点 | 可演示 | 冒烟 16–18（3 题入库，全部带「主考」标注，可按知识点筛选） |
| 15 | 按意图生成互动内容并在新标签页打开 | 可演示 | 冒烟 19（`inline=true` 回 `<!DOCTYPE html>`） |
| 16 | 上传 PDF/Word/PPT/图片/视频/录音 | 可演示 | 冒烟 3–7 覆盖 PDF/Word/图片/视频；PPT 与录音由 `tests/test_documents_workbench.py`、`test_audio.py` 覆盖（六路解析器齐备） |
| 17 | 看到文档解析状态 | 可演示 | 冒烟 4–7（处理中 → 已完成）；界面自动跟进（人工清单 1.2） |
| 18 | 把文档标记为参考资料 | 可演示 | `PATCH /documents/{id}/reference`（`test_documents_workbench.py`） |
| 19 | 图谱页可视化查看知识图谱 | 可演示 | 冒烟 20（数据面：8 节点 4 关系）；**渲染画面**需人眼（人工清单 1.4，本机无 Playwright） |
| 20 | 按学科/章节过滤图谱 | 可演示 | `GET /knowledge/graph?subject=&chapter=`（`test_graph_workbench.py`） |
| 21 | 点节点看详情（内容/难度/来源） | 可演示 | `GET /knowledge/nodes/{id}`（`KnowledgePointDetail` 带来源引用） |
| 22 | 从节点展开邻域子图 | 可演示 | `GET /knowledge/nodes/{id}/neighborhood?depth=1..3` |
| 23 | 冲突队列看到新旧知识对照卡片 | 可演示 | 冒烟 21–22（种子数据；定义冲突由检测自然产出，需真 Key） |
| 24 | 结构冲突看到「图谱现状 vs 三种裁决终态」图示 | 可演示（**检测未实现**） | 冒烟 22（`structure_preview.outcomes` = 接受新/保留旧/并存）；检测逻辑属 ADR-0006 范围外，用种子数据验证形态与动作 |
| 25 | 常识存疑照常入库/拒绝/编辑修正后入库 | 可演示（**检测未实现**） | 冒烟 24（编辑修正后入库 → 终态已接受）；同上，检测属范围外 |
| 26 | 浏览题库并按考查知识点筛选 | 可演示 | 冒烟 18（`?knowledge_point=` 筛选后 1 题） |
| 27 | 设置页从供应商目录选并粘贴 Key | 可演示 | `GET /settings/catalog` + `PUT /settings`（假 Key 即可建实现；**真实联通性**见人工清单 2.2） |
| 28 | 按任务选不同档位的模型 | 可演示 | `model_for()` + `GET/PUT /settings` 的 `tasks`（`test_settings_api.py`） |
| 29 | 添加自定义 OpenAI 兼容服务 | 可演示 | 目录里的 `custom` 档（`accepts_any_model=true`） |
| 30 | 改完立即生效、Key 回读只见掩码 | 可演示 | 写穿用例 `test_capability_switch_takes_effect_without_restart`；掩码 `mask_key()`（回读无明文） |
| 31 | 无 Key 时全功能可跑（stub 模式） | 可演示 | 本票冒烟全程无 Key，25 步全过 |
| 32 | 换任何云端能力只改配置不改代码 | 可演示 | 能力注册：接口 + 工厂 + stub（`test_capability_registry.py`）；设置页即配置 |
| 33 | 检索与分块策略可插拔 | 可演示 | `tests/test_rag_strategies.py` 用 `marked` 实现零改动接入管道 |
| 34 | 接口文档与代码永远同步（OpenAPI 单一事实源） | 可演示 | `/openapi.json` + `test_openapi_contract.py`（含本票新增的响应模型守卫）+ 前端类型由它生成 |
| 35 | 仓库自带分层规范（AGENTS/风格/ADR/词汇表） | 可演示 | `AGENTS.md`、`backend/AGENTS.md`、`frontend/AGENTS.md`、`docs/style/`、`docs/adr/`、`CONTEXT.md`；本票补 `docs/acceptance-manual.md` |
| 36 | AI 代理进仓库即知硬规则与验收标准 | 可演示 | `AGENTS.md` 的必读指针 + README 新增「文档地图」+ 人工清单 |

**结论**：36 条全部有实现与证据；其中 3 条（#4/#5 澄清与跳过追问、#24/#25 两类的**检测逻辑**）
在**本机环境（无 Key / 无浏览器 / 检测属范围外）**看不到，已分别指向「真 Key 人工清单」与 ADR-0006，
不计入「已演示」。没有「未实现且未写原因」的条目。

### 七、文档一致性（README / 架构一页图 / 接口专题）

| 文档 | 改了什么 / 核对了什么 |
| --- | --- |
| `README.md` | 启动步骤**实测可跑**（见第一节）；「产物」等禁用写法改掉；架构图改成六区 + 后端分层并与 `docs/architecture.md` 对齐；新增「文档地图」并链到人工清单 |
| `docs/architecture.md` | 六区端点表从「现状 → 目标」改为**当前端点**（去票号）；「现状与目标」节重写：已实现 / 未实现（ADR-0006 检测）/ 已登记落差，并把两类人工验收指向人工清单 |
| `docs/api/stub-mode.md` | **改掉「网络搜索无 stub」的错误说法**（stub 存在且已注册，无 Key 即回落占位结果；显式配 `bocha` 缺 Key 才是 500）；新增「stub 模式下走不到的分支」（澄清回复 / 自然冲突 / 真实提取内容） |
| `docs/api/artifacts.md` | 修改端点补全为**五类**（`/revise`、`/revise/word`、`/revise/outline`、`/revise/exam`、`/revise/interactive`），并说明「历史版本一律可作基线」在五类上都成立 |
| `backend/app/api/v1/knowledge.py` | 网络搜索端点的描述同步改写（原文写「本能力无 stub 实现」，与实现不符） |
| `docs/acceptance-manual.md` | **新建**：三节（真浏览器逐区点选 / 真实 Key 联通性 / 人眼视觉项）+ 附录 A stub 冒烟命令 + 附录 B 冲突种子脚本；README 已链接 |

### 八、改动文件清单

#### 后端

- `backend/tests/conftest.py`：密封块（7 项能力配置 + 密钥置空），文件头补说明
- `backend/app/api/health.py`、`backend/app/main.py`、`backend/app/api/v1/router.py`：`HealthResponse` / `RootResponse` / `PingResponse` + `response_model`
- `backend/app/api/v1/knowledge.py`：`WebSearchResult` / `WebSearchResponse` + `response_model`；网络搜索描述改为与实现一致
- `backend/app/api/v1/settings.py`：删掉重复定义的 `_capabilities()`（票 13 报告项）
- `backend/tests/test_openapi_contract.py`：新增 `test_json_endpoints_declare_a_response_model` 回归守卫

#### 前端

- `frontend/openapi/openapi.json`、`frontend/src/api/generated/*`：`npm run gen:api` 重新生成
- `frontend/src/api/system.ts`：`apiRequest<unknown>` → 生成的 `PingApiV1PingGetResponse`，并改掉「`/health` 不带 schema」的过时注释

#### 文档

- 新建 `docs/acceptance-manual.md`；改 `README.md`、`docs/architecture.md`、`docs/api/stub-mode.md`、`docs/api/artifacts.md`

#### 票

- 本文件（勾选 + 交付记录）；`.scratch/restructure/issues/15-llm-vision-stub.md`（更正「网络搜索无 stub」那句）

**未改**（本票是收口，不是重构）：`CONTEXT.md` 的既有词条语义、各区的既有交互行为、`feature` 行为语义、
`db/models.py`、`app/core/**`（除 `settings.py` 去重）、任何 provider 实现。

### 九、登记在案的遗留清单：逐条判断

| 遗留 | 判断 | 理由 |
| --- | --- | --- |
| `settings.py` 的 `_capabilities()` 重复定义两处（票 13） | **修掉** | 纯删除，行为不变（334 passed） |
| 票 15 交付记录「网络搜索依旧无 stub」这句是错的 | **修掉** | 只改一句话，已在 15 的票文件里更正 |
| 票 12：`questions` 表缺 `analysis` 字段（题目详情不展示解析） | **留待后续** | 需要改 `db/models.py`（**不在本票 ownership**）、幂等补列、题库详情响应模型与详情区展示——是行为变更而非收口；补列方案与理由已写清：加列 + `db/engine.py` 幂等补列 + `QuestionDetail.analysis` |
| 票 11：`/conflicts/:conflictId` 详情路由仍是占位 | **留待后续** | 是新增功能（新端点 + 前端详情区），不在「收口」范围；队列与裁决主路径可用，用户故事 23–25 不依赖它 |
| 票 11：冲突队列不分页 | **留待后续**（无阻塞） | 单用户个人知识库量级；分页会改响应形状，属契约变更 |
| 票 10：图谱画布无分页/虚拟化 | **留待后续**（无阻塞） | 前端性能优化，不影响正确性；节点规模由个人资料量决定 |
| 票 10：来源引用只到资料粒度 | **留待后续** | 要做到段落级要给分块保留引用串，属检索层改造（ADR-0003 之外的新决策） |
| 票 09：资料列表无分页；详情只回前 200 个分块 | **留待后续**（无阻塞） | 同上（量级 + 契约形状） |
| 票 08：会话累积意图无读端点 | **留待后续** | 一键试卷/互动内容用弹层主题组装 intent 已够用；新增读端点是新契约 |
| 票 08：课件修改回退默认配色（`style` 未随版本留痕） | **留待后续** | 要改版本内容快照的形状（写 `style` 进 content），属行为/契约变更 |
| 票 08：无版本级删除与落盘回收 | **留待后续** | 需要删除端点 + 文件回收策略（含「删会话不删文件」的既有口径），是本批之外的功能 |
| 票 01：`db/models.py` 指向不入库 DESIGN.md 的断链 | **无需处理** | 已由票 05 修掉 |
| `data/output` 是测试共享落盘路径 | **留待后续**（已在 README/人工清单说明） | 隔离它需要给生成器注入输出目录（改 `generate/**`，不在本票 ownership）；测试本身不写 `data/output` 以外的开发数据 |

> 本票**没有**为了「看起来干净」而顺手修行为类遗留：收口的价值在于把现状讲准，而不是扩大改动面。

### 十、本票未做（明确由人工承接）

- **真浏览器点选**：本机无 Playwright（测试决策明写「组件测试 / 端到端测试基建属范围外」），逐区点选步骤、预期现象、失败判据全部写进 `docs/acceptance-manual.md` 第 1 节。
- **真实云端 Key 联通性**：本机无 Key，`docs/acceptance-manual.md` 第 2 节给出 `backend/scripts/verify_services.py` 的跑法、逐家配置表与报错对照表。
- **人眼视觉项**：机器能扫的（禁用 class 10 条规则）已零违规，其余（悬停反色、四态、密度、mermaid 扁平主题、空/加载/失败三态）列成勾选清单，见第 3 节。

## 协调者复核

**结论：通过（本批最后一张，逐条复核到「酸测试」级别）。** 复核人 = 协调者（主代理），2026-09-24。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| stub 模式全链路冒烟 | 交付记录的真 uvicorn + 真 HTTP 冒烟 25/25（PDF/Word/图片/视频上传到终态、会话生成、版本列表/详情/下载、以历史版本为基线改一版、试卷入题库并带考查知识点、互动内容 inline、三类别冲突裁决） | 通过 |
| 风格自检清单 + 禁用类扫描零违规 | 协调者亲跑 `npm run lint`（104 文件零违规）+ `npm run build` | 通过 |
| 规格用户故事逐条核对 | 票内核对表（可演示 / 可解释 / 未实现+原因），未夸大：结构冲突与常识存疑的**检测逻辑**如实标注未实现（ADR-0006） | 通过 |
| README、架构图、接口专题与现实一致 | README 启动步骤实测可跑；`docs/architecture.md` 落差节、`docs/api/*` 已对齐；票 15 那句错说法已更正 | 通过 |
| 后端测试全绿、主干按 README 可跑 | 见下方酸测试 | 通过 |
| **【追加·测试密封性】** | 见下方酸测试；`backend/tests/conftest.py` 用 `os.environ.setdefault` 钉住 stub 档能力配置并置空云端 Key | 通过 |
| **【追加·补齐响应模型】** | 协调者独立盘点：37 个操作中**仅剩 2 个文件下载端点**无 JSON 响应模型（正当例外），并带回回归守卫用例 | 通过 |

**酸测试（协调者在主干上，不做任何环境钉法）**：主干存在真实 `backend/.env`（`LLM_PROVIDER=dashscope` + 真实 Key）。
- 修复前同一状态：**805 秒 + 3 条假失败**（断言 stub 固定产出的用例跑在真实 provider 上）。
- 合并本票后：**334 passed / 12.3 秒**，`ruff check .` 干净；`settings.llm_provider` 仍为 `dashscope`，证明未改动 `.env`。**测试套件自此不再随开发者环境漂移。**

**本票最有价值的产出（协调者认定）**：不只是「跑通了」，而是**把「跑通」的边界写清楚了** —— 发现并文档化了「stub 模式下走不到的分支」（stub 意图固定且要素齐全 ⇒ 澄清回复走不到；比对恒「无矛盾」且两类检测未实现 ⇒ 冲突不会自然出现），冒烟因此使用种子数据并如实标注；`docs/api/stub-mode.md` 新增该节。这避免了「演示看着过、换真实 Key 就崩」的假绿灯。

**留给人的那一部分（按用户裁决）**：真浏览器逐区点选、真实云端 Key 联通性、人眼视觉项，全部落到新建的 `docs/acceptance-manual.md`（逐区步骤 / 预期现象 / 失败判据 / `verify_services.py` 跑法 / stub 冒烟附录 / 冲突种子脚本），并由 `README.md` 两处链接。

- **合并点**：`35089ba`（`merge(14)`），与主干无冲突；合并后重生成派生物无差异（快照自洽）；主干前端 `lint`/`build` 绿。
- **状态迁移**：`ready-for-agent` → `done`。
- **登记项逐条处置**：`questions.analysis`、`/conflicts/:conflictId` 占位、各类分页、版本回收、课件 `style` 未随版本留痕等，均在票内给了「留待后续 + 理由」；本票不夹带行为变更。
