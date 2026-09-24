# 07: 生成物全版本留痕

**What to build:** 每次生成物产出都作为版本入库：教师可列出某次备课的全部生成物历史版本、回看任意版本、下载任意版本、以任意历史版本为基线继续修改——修改产生新版本而非覆盖旧版。落盘文件与版本记录一一对应，可按版本取回正确文件。本票交付到 HTTP 层可演示。

**Blocked by:** 05 会话持久层 + 状态机收编

**Status:** ready-for-agent

- [x] 生成即入库，同一会话内版本号单调递增
      （新表 `artifact_versions`；`test_each_generation_records_a_version_with_monotonic_numbers`、
      `test_generation_versions_are_written_to_the_database`）
- [x] 版本列表 / 详情 / 下载 API 可用
      （`GET /api/v1/sessions/{session_id}/artifacts`、`GET /api/v1/artifacts/{version_id}`、
      `GET /api/v1/artifacts/{version_id}/download`；`test_version_detail_and_download_return_that_versions_own_file`）
- [x] 以历史版本为基线的修改产生新版本，原版本保持可取
      （`POST /revise`、`POST /revise/word` 纯新增可选 `session_id` / `base_version_id`；
      `test_revise_from_a_historical_version_creates_a_new_version_and_keeps_the_old_one`）
- [x] 落盘文件与版本记录一一对应，可按版本取回正确文件
      （`test_versions_and_files_are_one_to_one`、下载字节与回读 pptx 内容双重核验）
- [x] 全部经 HTTP 缝测试，测试只断言响应与数据变迁
      （`backend/tests/test_artifact_versions.py` 19 例：只走 `TestClient` 与库/落盘读回，
      不替换任何内部函数，LLM 走无 Key 的 stub 兜底）

## 交付记录

**一句话**：新增生成物版本表 `artifact_versions` 与三个版本端点（列表 / 详情 / 下载），
一次备课的每件产出（课件 / 教案 / 提纲 / 试卷 / 互动内容）都在产出当刻落一条版本记录并对应一个落盘文件；
`POST /revise` 与 `POST /revise/word` 纯新增可选 `session_id` / `base_version_id`——以历史版本为基线再修改会产出版本号更高的
**新版本**，基线版本的文件与内容原样保留，不带会话时两个老端点的字段语义与行为一字未变。

**分支 / commit**：`JulianZBY/issue-07-artifact-versions`。代码 + 测试 + 文档所在的提交对象 = `fcba650`
（`git show fcba650 --stat` 可核对，15 个文件）；其后若另有提交，只补本交付记录与勾选，不动代码。
基线 `e68f872`（票 05 合入后的工作树尖端）。未 push、未开 PR、未 merge/rebase。

**新增文件**

| 文件 | 职责 |
| --- | --- |
| `backend/app/db/artifacts.py` | 持久层 `ArtifactStore`：版本记录的 ORM 读写、版本号推导、会话清理（无业务判断） |
| `backend/app/core/artifacts.py` | 生成物全版本留痕的用例层：生成即入库、基线解析、修改入库、产物回填版本标识 |
| `backend/app/api/v1/artifacts.py` | 三个版本端点（完整 OpenAPI 注解 + `response_model`，tag = 生成物） |
| `backend/tests/test_artifact_versions.py` | 版本留痕的 HTTP 缝用例（19 个） |

**改动**

- `backend/app/db/models.py`：**末尾追加** `ArtifactVersion`（所属会话 / 生成物类别 / 版本号 / 产出方式 / 基线
  `parent_id` / 落盘文件名 / 标题 / 内容快照，字段带中文语义注释，`user_id="default"`），
  并对 `(session_id, artifact_type, version)` 加唯一约束兜底「版本号不重复」；该表所用的
  `UniqueConstraint` 让本文件顶部 `from sqlalchemy import (...)` 变成括号多行（与并行票改动同一行的可能性存在）。
- `backend/app/core/orchestrator.py`：提纲改为与课件 / 教案同形——正文 + **落盘 .docx**（`outline` 字段从字符串
  变成 `{text, path, filename}`），生成失败时不渲染、不留半成品文件。这是本票唯一的既有产物形状变化，
  与票 01 已在 `chat.py` 响应示例里写明的 `outline: {"path": ...}` 目标形态对齐。
- `backend/app/generate/outline.py`：新增 `render_outline`（Markdown 提纲 → .docx，`#`/`##` 映射标题层级）。
- `backend/app/generate/__init__.py`：新增 `output_dir()`（调用时读模块属性，测试可重定向）——
  版本下载端点据此解析落盘目录，与生成器写入的是同一个目录。
- `backend/app/core/session_service.py`：会话内一轮生成后逐件落版本并把 `version_id` / `version` 回填进
  `artifacts`（会话工作台与版本中心同一份数据）；删会话时连同其版本记录一起清掉，不留无主版本行。
- `backend/app/api/v1/revise.py`：两个请求体**纯新增**可选字段 `session_id` / `base_version_id`，两个响应体**纯新增**
  `version_id` / `version` / `session_id`；两个端点的路径、既有字段与不带会话时的行为未动。
- `backend/app/api/v1/exam.py` / `backend/app/api/v1/interactive.py`：请求体纯新增可选 `session_id`，
  响应体纯新增 `version_id` / `version` / `session_id`；带会话时试卷 / 互动内容走同一条版本入库路径，
  会话不存在先 404（不白跑生成、不留无主记录）。
- `backend/app/api/v1/router.py`：只追加一行 `include_router`（并行票纪律）。
- `docs/api/artifacts.md`：版本语义从「目标语义 + 实现状态（随票 07 交付）」改写为**已交付语义**，
  补三个端点的用途表、`parent_id` 版本树口径、删除会话对版本记录的影响；相关端点清单补三行。
- `docs/architecture.md`（仅「现状与目标（落差说明）」节）：票 05/07 与票 02/03 从「未实现」移入「已实现」
  （票 02/03 已合入基线，原表述已过期），未实现清单改为票 06/08~14 + ADR-0004 的两类检测逻辑。

**跑过的命令与结果**

```text
cd backend
uv sync                                     # 全新工作树，无 setup 钩子
uv run pytest -q                            # 239 passed（基线 214：+19 本票用例 +6 新端点自动进 OpenAPI 契约用例）
uv run ruff check .                         # All checks passed!
uv run pytest tests/test_artifact_versions.py -v   # 19 passed（逐条名字见下）
uv run pytest tests/test_openapi_contract.py -q    # 54 passed（3 个新端点 × documented / error_code 等断言）
```

真机冒烟（真 uvicorn + 真 HTTP + stub 全链路，临时库 / 临时落盘，不碰开发库）：

```text
建会话: 200 a0d1a719-…
对话: 200 clarifying= False version= 1
首轮版本: 200 {'课件': [1], '教案': [1], '提纲': [1]}
第 1 版下载: 32873 字节， courseware_ppt_d863546b.pptx
以第 1 版为基线修改: 200 新版本= 2 基线= 576f8c40-…
修改后课件版本: [1, 2] current= 2
新版本由第 1 版衍生: True
原版本仍可取回且字节未变: True
新版本详情: 200 title= TCP 三次握手 file= courseware_ppt_dd0b0718.pptx origin= 修改
```

（冒烟脚本与临时库在 `%TEMP%` 下，跑完即删；它在 `backend/data/output` 留下的 8 个冒烟文件已按时间戳删除干净。）

**证据：19 个 HTTP 缝用例**（`uv run pytest tests/test_artifact_versions.py -v`，全部 PASSED）

| 验收点 | 用例 |
| --- | --- |
| 生成即入库 + 版本号单调递增 | `test_each_generation_records_a_version_with_monotonic_numbers`（两次生成 → 课件/教案/提纲各 [1, 2]，第 2 版 `parent_id` = 第 1 版，文件名互不相同且都在盘上）、`test_generation_versions_are_written_to_the_database`（库内行：`user_id=default`、版本号不重复且有序） |
| 会话与版本中心同一事实源 | `test_generation_message_carries_version_ids`（生成回复的 `ppt` / `word` / `outline` 都带回 `version_id`，与列表里的 id 相等） |
| 列表 / 详情 / 下载 | `test_version_detail_and_download_return_that_versions_own_file`（详情带该版内容快照；下载字节 = 该版落盘文件字节；回读 pptx 每页文本与第 1 版快照逐个对上）、`test_download_supports_inline_for_interactive_content`（`inline=true` 无下载头、正文是那段 HTML）、`test_artifact_type_filter_and_unknown_versions`（类别过滤、空组、未知会话 / 版本 404、非法类别 422） |
| 一一对应 | `test_versions_and_files_are_one_to_one`（3 轮生成 → 每条记录都有唯一文件，且由 filename 反查回同一个版本 id） |
| 以历史版本为基线修改 | `test_revise_from_a_historical_version_creates_a_new_version_and_keeps_the_old_one`（第 2 版在手时以第 1 版为基线 → 产出第 3 版，`origin=修改`、`parent_id`=第 1 版；第 1 版字节未变、仍可下载、详情仍是第 1 版；新版本下载回读的是改后内容）、`test_revise_word_from_a_historical_version_records_a_version`（教案同模式）、`test_revise_uses_current_version_when_only_session_is_given`（只给会话 → 以当前版本为基线）、`test_revise_rejects_unknown_or_mismatched_baseline`（未知版本 / 未知会话 404，拿教案版本改课件 422）、`test_revise_on_session_without_that_artifact_returns_404`（无基线不做无基线的修改） |
| 既有语义不变 | `test_revise_without_session_keeps_existing_behaviour`（不带会话：只回文件名，不落版本记录、`version_id` 为空）、`test_exam_generation_without_session_keeps_existing_behaviour`（试卷照旧出题入库落盘） |
| 五类生成物都留痕 | `test_exam_and_interactive_generation_record_versions`（试卷 [1, 2] 单调递增 + 题目快照可下载；互动内容带会话入库并可内联打开） |
| 会话清理 | `test_deleting_a_session_removes_its_version_records`（删会话 → 版本记录一并消失，列表 404） |
| 错误码 | `test_generation_with_unknown_session_returns_404`（带了不存在的会话不静默丢弃版本记录） |
| 接口纪律（票 04 的欠账） | `test_new_endpoints_declare_a_response_model`（3 个新端点 + 两个 revise 端点 + 试卷 / 互动内容的 200 响应都有 schema；版本下载是二进制流，与既有 `GET /files/{filename}` 同口径只注解 `responses`）、`test_artifact_endpoints_are_documented_with_examples`（summary / 描述 / 示例 / 错误码 / tag = 生成物） |

**缺省行为说明（不带会话标识时）**

- 生成 / 修改请求不带 `session_id`（且不带 `base_version_id`）时，行为与票 05 收编后完全一致：
  照旧产出文件、返回 `filename`，`version_id` / `version` / `session_id` 为 `null`，不落版本记录。
  理由：版本由「某次备课」承载，无会话即无归属；无状态对话路径（`POST /chat` 不传 `session_id`）同理，
  其既有行为「不落库、不回显会话 id」由既有用例继续守住。
- 带 `session_id` 时校验会话存在（404），带 `base_version_id` 时校验版本存在（404）与类别一致（422）；
  `base_version_id` 与 `session_id` 同时给出且不属于同一会话时 422。

**`data/output` 使用面变化**

- 本票让**提纲**也落盘（此前只有课件 / 教案 / 试卷 / 互动内容写文件），并新增 `output_dir()` 供版本下载端点
  解析目录；测试的落盘隔离沿用 conftest 的 `isolated_output_dir`（本票新用例全部经它重定向，不写
  `backend/data/output`）。既有 `test_exam_api.py` / `test_interactive_api.py` 仍直接共用
  `backend/data/output`（票 02 登记的既有共享落盘），本票未扩大也未收口；跑全套测试会在那里留下文件
  （`data/output` 已被 `.gitignore` 忽略，`git status` 始终干净）。

**并发的写冲突**

- 版本号由「同一会话 + 同一生成物 + 同一版本号」的唯一约束兜底：并发产生同号时数据库拒绝写入而不是静默覆盖。
  单用户本地场景不做更重的串行化（无分布式锁、无重试），这是本票的显式取舍。

**两轴自审**

- Standards：分层铁律（`api/v1` 只做参数校验 / 转发与响应映射，版本与基线的判断住 `core/artifacts.py`，
  ORM 读写住 `db/artifacts.py`，新表进 `db/models.py` 且字段带中文语义注释、单用户 `user_id="default"`）；
  接口纪律（3 个新端点带 summary、描述、请求 / 响应示例、错误码、tag=生成物、`response_model`）；
  `uv run ruff check .` 干净；测试只替换外部能力（本票连能力都没替换，全链路走 stub）；面向教师的文案用
  `CONTEXT.md` 术语（生成物 / 版本 / 当前版本 / 历史版本 / 基线 / 「第 N 版」/ 生成 / 修改），
  未出现「旧版本被覆盖」「修改即替换原文件」这类与全版本留痕相反的措辞；
  并行纪律：`router.py` 只追加一行，`models.py` 只追加到末尾，未重排既有 import 与代码块。
- Spec：五条验收项与「每次生成物产出都落一条版本记录」「版本号单调递增」「版本 ↔ 文件一一对应」
  「可按版本取回正确文件」「修改产生新版本而非覆盖旧版」逐条对上（证据表），
  未做前端（票 08）、未改本票以外的 `.scratch/**` 与 `CONTEXT.md`；`docs/api/artifacts.md` 与
  `docs/architecture.md` 落差节已回校，与代码一致。

**遗留问题**

1. 前端 `frontend/src/api/generated/types.gen.ts` 尚未重新生成，新端点 / 新字段还不在类型里（生成与前端都归
   票 04/08；本票按范围未动 `frontend/**`）。
2. 删会话只删版本记录，不回收 `data/output` 里的落盘文件（本仓库尚无文件回收机制），已在
   `docs/api/artifacts.md` 写明；文件回收需要一个独立决策（何时清、按会话还是按年龄）。
3. `docs/architecture.md` 六区表里「生成物」一行仍写「→ 版本列表 / 详情 / 下载（票 07/08）」——
   本票按 Ownership 只改落差说明节，未动该表。
4. `artifacts.outline` 由字符串变为对象（`{text, path, filename}`），票 06/08 的前端消费点需按此取值
   （已有 `docs/api` 与 `chat.py` 响应示例此前就按对象形态写的）。
5. 版本号并发同号由唯一约束兜底（拒绝写入），没有重试；单用户本地场景可接受，多进程部署前需要重看。
