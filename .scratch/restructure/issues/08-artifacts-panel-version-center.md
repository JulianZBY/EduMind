# 08: 生成物面板与版本中心

**What to build:** 生成结果就在对话旁：并排预览课件、教案、提纲，下载课件与教案；对单个生成物提修改意见再生成（只作用所选生成物、产生新版本）；一键生成试卷且题目自动入题库并标注考查知识点；按意图生成互动内容并在新标签页打开；生成物区独立浏览全部备课的生成物——按会话分组的时间线，任意历史版本可回看、可下载、可以此为基线继续修改，「上次那版更好，找回来」成为一步操作。

**Blocked by:** 06 备课会话工作台; 07 生成物全版本留痕

**Status:** done

- [x] 预览 / 下载 / 修改意见 / 一键试卷 / 互动内容五类操作全部可用
- [x] 修改意见只作用于所选生成物，且产生新版本
- [x] 试卷生成后题目入题库，可按考查知识点查到
- [x] 各生成过程有进行中 / 失败态，失败可重试
- [x] 生成物按会话分组，版本时间线清晰可辨
- [x] 会话工作台与生成物区的版本数据一致（同一事实源）
- [x] 方向性调整的引导提示仍保留在对话区

## 交付记录

**一句话**：备课会话区在对话轴**旁边**挂上「生成结果」面板——并排预览课件 / 教案 / 提纲的**当前版本**、
一键下载、对**单个**生成物提修改意见（产出新版本）；生成物区从占位页长成版本中心——二级侧栏按备课会话分组、
主区是这次备课的版本时间线（当前版本与全部历史版本并列、任意版本可回看 / 可下载 / 可「以此版为基线修改」）、
右侧列回看这一版的内容快照；两个区读的是**同一份版本数据**（同一个 hook、同一个 query key、同一条版本端点）。
为让「历史版本一律可作基线继续修改」这条 `CONTEXT.md` 硬约束对五类生成物都成立，后端**追加**了三个修改端点
（提纲 / 试卷 / 互动内容），请求体与既有两个修改端点同形：只带所选这一版的内容 + 修改意见 + `base_version_id`。

**分支 / commit**：`JulianZBY/issue-08-artifacts-panel`。代码 + 测试 + 类型产物的提交对象 = `b253a88`
（`git show b253a88 --stat` 可核对，22 个文件）；其后仅补本交付记录与勾选的提交不动代码。基线 = 本工作树切出时的尖端。
未 push、未开 PR、未 merge/rebase。

**新增文件**

| 文件 | 职责 |
| --- | --- |
| `backend/tests/test_artifact_revision_paths.py` | 五类生成物「修改意见」路径的 HTTP 缝用例（5 例，stub 全链路 + 落盘隔离） |
| `frontend/src/areas/artifacts/queries.ts`（重写） | 生成物区服务端状态：版本列表 / 版本详情 / 五个修改端点 / 一键试卷 / 互动内容；`artifactKeys` |
| `frontend/src/areas/artifacts/narrowing.ts` | 纯函数：内容快照的白名单读法、版本组读法、修改请求组装、失败说法、意图组装 |
| `frontend/src/areas/artifacts/routes.ts` | 生成物区地址（`/artifacts/:sessionId?v=`，URL 即状态） |
| `frontend/src/areas/artifacts/ArtifactPreview.tsx` | 按类别呈现某一版的内容快照（课件 slides / 教案结构 / 提纲正文 / 题目 / 互动内容 HTML） |
| `frontend/src/areas/artifacts/VersionTimeline.tsx` | 一条生成物时间线：每行 = 回看 / 下载 / （互动内容）新标签页打开 / 以此版为基线修改 |
| `frontend/src/areas/artifacts/ReviseDialog.tsx` | 修改意见弹层（读取所选版本 → 填写 → 进行中 / 失败可重试）；两个区共用 |
| `frontend/src/areas/artifacts/SessionVersionCenter.tsx` | 生成物区主区：版本时间线 + 回看列；一键试卷 / 互动内容入口 |
| `frontend/src/areas/artifacts/ArtifactsSidebar.tsx` | 生成物区二级侧栏：按会话分组 + 版本计数 + 按标题检索 |
| `frontend/src/areas/artifacts/GenerateDialogParts.tsx` | 两个按需生成弹层共用的界面件（进行中条 / 生成后入口 / 意图的可选字段） |
| `frontend/src/areas/artifacts/GenerateExamDialog.tsx` | 一键生成试卷弹层（题量 1–20；成功后下载 + 去题库） |
| `frontend/src/areas/artifacts/GenerateInteractiveDialog.tsx` | 按意图生成互动内容弹层（成功后新标签页打开试用） |
| `frontend/src/areas/lesson-prep/GenerationPreview.tsx` | 对话旁的并排预览面板（课件 / 教案 / 提纲三列 + 试卷 / 互动内容紧凑行 + 修改意见入口） |

**改动**

- `backend/app/api/v1/revise.py`：**追加**三个端点 `POST /revise/outline`、`POST /revise/exam`、`POST /revise/interactive`
  （完整 OpenAPI 注解：summary / 描述 / 请求响应示例 / 错误码 / tag=生成物，全部带 `response_model`），
  复用既有 `_resolve_baseline` 与 `core/artifacts.record_revision`，既有两个端点的路径、字段与行为未动；
  import 块只追加行。
- `backend/app/generate/revise.py`：**追加** `revise_outline` / `revise_exam` / `revise_creative` 与三条提示词。
  共同不变式「模型没给出可用结果时保留基线内容」——宁可产出一版内容不变的产出，也不产出一版坏内容
  （提示词里刻意保留 stub 命中的关键词，无 Key 时三条修改路径同样可跑）。
- `frontend/src/areas/artifacts/index.tsx` / `ArtifactsArea.tsx`：二级路由 `:artifactId` → `:sessionId`；
  占位页（`AreaStub`）换成真实的版本中心。
- `frontend/src/areas/lesson-prep/LessonPrepArea.tsx`：会话视图由「只渲染对话轴」变成「对话轴 + 并排预览」
  （仅在轴旁挂面板，`ConversationAxis` / `ConversationTranscript` / `ConversationComposer` 一行未改）。
- `frontend/src/areas/lesson-prep/queries.ts`：`useSendTurn.onSettled` 追加两行缓存失效（`artifactKeys.sessionArtifacts()`、
  `artifactKeys.versions()`）——一轮对话可能产出新版本，让并排预览与生成物区一起跟上；发送 / 重试 / 乐观改写的行为未动。
- `frontend/openapi/openapi.json`、`frontend/src/api/generated/**`：`npm run gen:api` 重新生成（三个新端点进类型）。

**跑过的命令与结果**

```text
cd backend
uv sync                                            # 全新工作树，无 setup 钩子
uv run ruff check .                                # All checks passed!
uv run pytest -q                                   # 333 passed（基线 328：+5 本票用例 +3 新端点自动进 OpenAPI 契约用例）
uv run pytest tests/test_artifact_revision_paths.py -q   # 5 passed

cd frontend
npm install                                        # 全新工作树，node_modules 不在版本控制内
npm run lint                                       # 禁用 class 扫描：104 个文件、10 条规则零违规；oxlint 无输出
npm run build                                      # check:classes + tsc -b + vite build 全绿
npm run check:routes                               # 七条路由可达 + 逐条 SSR 渲染断言全绿
```

端到端实测（临时脚本 `frontend/.tmp-accept-08.mjs`，跑完即删）：**真 uvicorn（stub 能力 + 临时库 / 临时落盘）+
前端自己的数据层打真 HTTP + 把真响应塞进 Query 缓存后用 `react-dom/server` 渲染真路由**，**58 条断言全过**；
另起真 vite dev server，14 个新增 / 改动的模块逐个 `GET` 全部 `200`（含四态与样式扫描），`/artifacts` 返回可挂载页面。

**七条验收项的复现方式**

| 验收项 | 怎么复现 | 实测结果 |
| --- | --- | --- |
| 预览 / 下载 / 修改意见 / 一键试卷 / 互动内容五类操作全部可用 | `uv run pytest tests/test_artifact_revision_paths.py -q`（三条修改路径）+ 验收脚本 §2/§3/§4（真 HTTP：五个修改端点、`POST /exam/generate`、`POST /interactive/generate`、按版本下载 / inline 取回）；SSR §6 断言两个区都渲染出预览与下载 / 修改入口 | 通过 |
| 修改意见只作用于所选生成物，且产生新版本 | `test_revise_outline_from_a_historical_version_keeps_the_baseline_and_others`；验收脚本 §2：以课件第 1 版为基线改 → 课件 `[1,2,3]`、教案与提纲仍是 `[1,2]`、新版本 `parent_id` = 第 1 版、`origin=修改`、第 1 版字节未变、修改响应回的版本 id = 版本列表里的当前版本 | 通过 |
| 试卷生成后题目入题库，可按考查知识点查到 | `test_revise_exam_records_a_version_and_the_revised_questions_enter_the_bank`（改后的题目逐条查详情带考查知识点，且按 `TCP滑动窗口` 筛得出来）；验收脚本 §3：`bank_saved=3`，`GET /questions?knowledge_point=TCP滑动窗口` 返回题目且每条都带考查知识点 | 通过 |
| 各生成过程有进行中 / 失败态，失败可重试 | 验收脚本 §5（给不存在的会话生成 → `404`；拿教案版本当课件基线 → `422`，界面据此给说法）+ §7（空缓存下两个区与并排预览都渲染「正在读取…」进行中态；对话区「这一轮没跑完 / 重试这一轮」；生成物取数失败「重试」）+ `test_revision_rejects_unknown_or_mismatched_baseline` | 通过 |
| 生成物按会话分组，版本时间线清晰可辨 | 验收脚本 §6：侧栏「按会话分组」+ 计数，时间线里「第 1/2/3 版」+「当前版本 / 历史版本」+「由第 1 版衍生」+「以此版为基线修改」；按版本寻址（`?v=`）回看试卷 / 互动内容的内容快照 | 通过 |
| 会话工作台与生成物区版本数据一致（同一事实源） | 结构上两处调的是同一个 `useSessionArtifacts`（`artifactKeys.sessionArtifact(sessionId)`，只有票 07 的 `GET /sessions/{id}/artifacts` 一条端点）；验收脚本 §6 只给缓存塞**一个**版本列表条目，两个区渲染出的版本号集合互相覆盖；`test_generation_message_carries_version_ids`（票 07）继续守住「生成回复带的版本 id = 版本列表里的 id」 | 通过 |
| 方向性调整的引导提示仍保留在对话区 | 验收脚本 §6：会话区渲染出「跳过追问，直接生成」「回车发送」；生成物区渲染结果里**不含**「跳过追问」「直接生成」；`ConversationAxis` / `ConversationTranscript` / `ConversationComposer` 本次一行未改（`git diff` 可核对） | 通过 |

**设计取舍（写清理由，便于复核）**

1. **三个新修改端点**：`CONTEXT.md` 第 3 节的硬约束是「历史版本一律可回看、可下载、可作基线继续修改」。票 07 只给了
   课件 / 教案两条修改路径，若只消费它们，试卷 / 互动内容 / 提纲的历史版本就无法「作基线继续修改」。因此按票内
   「新增路由一律追加」的授权补了三条同形端点（请求体：所选版本的内容 + 修改意见 + `base_version_id`），
   放在既有 `revise.py` 末尾，既有端点一个字节未动。
2. **两个区共用一份版本数据**：版本数据的 hooks 住 `areas/artifacts/queries.ts`，备课会话区的并排预览直接引用它
   （跨区引用是刻意的）。这样「同一事实源」不是靠约定，而是**同一个缓存条目**：一处刷新，两处一起变；
   备课会话区不新增任何版本查询、浏览器里没有第二份版本列表。两个区各自的「会话列表」查询则各自持有
   （备课会话区用 `lessonPrepKeys`，生成物区用 `artifactKeys`，避免两区互相 import 成环）。
3. **生成物区按会话分组的计数**：版本端点按会话设计（票 07），因此侧栏对每个会话各发一次版本列表请求
   （`useQueries`，有缓存与结构共享）。没有新增「跨会话版本列表」端点——那会造出第二份版本事实源。
   单用户本地场景会话数量很小，这个取舍写在代码注释里。
4. **一键试卷 / 互动内容的意图**：服务端没有暴露「会话累积意图」的读端点，因此弹层让教师填/改主题（初值 = 会话标题）
   与可选学段、时长、互动诉求，组装成 `intent` 传回去（服务端 `intent` 本就是自由结构，缺字段退化为仅凭主题生成）。
   真正的「透传上次备课的累积意图」需要一个意图读端点，记入遗留问题。
5. **修改后重渲染的课件配色**：`style`（风格偏好）没有随版本留痕，所以修改课件时 `style` 传空、回退默认主题。
   内容层面的修改链路与版本语义不受影响，记入遗留问题。

**两轴自审**

- Standards：后端分层（`api/v1` 只做校验 / 转发 / 响应映射，提示词与渲染住 `generate/`，版本与基线的判断仍旧复用
  `core/artifacts.py`）；接口纪律（3 个新端点带 summary / 描述 / 请求响应示例 / 错误码 / tag=生成物 / `response_model`，
  `test_openapi_contract.py` 自动覆盖）；只追加不重排（`revise.py` 的两个既有端点与其 import 顺序未动）；
  `ruff check` 干净；测试只经 HTTP 缝断言响应与数据变迁、stub 全链路、落盘经 `isolated_output_dir` 隔离、无 `.env` 依赖。
  前端：一区一目录（生成物区新增 13 个文件、未改任何共享文件；`src/components/**` 一个字节未动、没有新增组件）、
  服务端状态一律 TanStack Query 且 key 以 `artifactKeys.all` 打头、**没有手抄接口类型**（地址与请求 / 响应形状全部取自
  `src/api/generated`）、风格硬标准（禁用 class 扫描零违规；悬停黑白反色、四态齐备、聚焦 `outline-black`、
  只用 `transition-colors duration-150`、无 emoji、进行中用「文字 + 直角进度条」、数据区工作台密度 / 空状态编辑密度）；
  面向教师的文案一律 `CONTEXT.md` 术语（生成物 / 版本 / 当前版本 / 历史版本 / 基线 / 修改意见 / 考查知识点 / 备课会话），
  未出现「产物」「旧版本被覆盖」这类写法。纯函数（内容读法、修改请求组装、版本组读法）与界面分文件，可脱离 React 核对。
- Spec：票内 7 条验收项逐条有复现方式与实测结果（上表）；`What to build` 的六件事逐件对上：
  并排预览 + 下载课件 / 教案（§6）、单个生成物修改意见产生新版本（§2）、一键试卷入题库按考查知识点可查（§3）、
  按意图生成互动内容并新标签页打开（§4 + §6）、生成物区按会话分组的版本时间线 + 历史版本回看 / 下载 / 作基线（§6）、
  各生成过程进行中 / 失败可重试（§7）；约束逐条遵守：不改票 06 对话轴行为、不改既有端点路径与字段语义、
  新增端点带完整注解与 `response_model`、改完接口重跑 `gen:api` 并提交生成产物、类型为 `unknown` 处做运行时收窄、
  真浏览器点选留给票 14。**未做**：本票范围外的知识库 / 图谱 / 题库 / 冲突 / 设置各区；未改 `CONTEXT.md`、`docs/**`、
  `.scratch/**` 里非本票文件。

**遗留问题**

1. **累积意图没有读端点**：一键试卷 / 互动内容目前按教师在弹层里填的主题（初值 = 会话标题）组装 `intent`，
   无法真正透传「这次备课累积的意图」。补一个会话意图读端点（或把意图并进会话摘要）才能做到。
2. **课件修改后回退默认配色主题**：`style`（风格偏好）没随版本留痕，因此「以历史版本为基线改课件」用默认主题重渲染。
   内容修改与版本语义不受影响；要保住配色需把生成时的 `style` 存进版本记录（属票 07 的数据模型范围）。
3. **历史版本不能逐版删**：本票没有删除版本 / 生成物的入口（票内未要求），`data/output` 的落盘文件也仍无回收机制
   （与票 07 登记的遗留同一件事）。
4. **生成物区未选中会话时没有「全部生成物」总表**：按会话分组是票内要求的结构，总览页只给「选一条备课会话」的入口。
   若要「一屏看全站最近产出」，需要一个跨会话的版本读口径（会引出第二份事实源问题，需先决策）。
5. **真浏览器点选未验**：本机无 Playwright，交互（勾选、点按钮、弹层焦点）按「导航与状态断言 + SSR 渲染」覆盖，
   留票 14 做端到端。

## 协调者复核

**结论：通过。** 复核人 = 协调者（主代理），2026-09-24。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| 预览 / 下载 / 修改意见 / 一键试卷 / 互动内容五类操作可用 | `frontend/src/areas/artifacts/{ArtifactPreview,ReviseDialog,GenerateExamDialog,GenerateInteractiveDialog}.tsx` + 会话区 `GenerationPreview.tsx` | 通过 |
| 修改意见只作用所选生成物且产生新版本 | 后端按票内授权追加 `POST /revise/outline|exam|interactive`（`response_model` + 「生成物」tag，既有端点未动）；58 条真 HTTP 断言含此条 | 通过 |
| 试卷题目入题库且可按考查知识点查到 | 复用票 12 的 `GET /questions?knowledge_point=`（未另造一套） | 通过 |
| 各生成过程有进行中/失败态、失败可重试 | 交付记录含失败重试断言 | 通过 |
| 生成物按会话分组、版本时间线清晰 | `ArtifactsSidebar.tsx` + `SessionVersionCenter.tsx` + `VersionTimeline.tsx` | 通过 |
| 会话工作台与生成物区版本数据一致（同一事实源） | 两区共用 `useSessionArtifacts` + 同一条票 07 版本端点 | 通过 |
| 方向性调整引导提示仍留在对话区 | 交付记录含该条断言 | 通过 |
| 测试与静态检查 | 协调者亲跑 333 passed、`ruff check .` 干净、前端 `npm run lint` + `npm run build` 绿、**工作树干净且无临时脚本残留** | 通过 |

**合并过程**：`merge-tree` 预探显示与主干**无冲突**（本批唯一一次全自动合并）。但协调者仍按惯例在合并后**重跑 `npm run gen:api` 并复跑全量**——生成类文件即便能自动合并也不保证语义自洽；随后确认再跑一次 `gen:api` 已无差异（快照幂等、含三个新 revise 端点）。

- **合并点**：`e3f68d5`（`merge(08)`）；合并后 main 复跑 → 333 passed + ruff 干净。
- **状态迁移**：`ready-for-agent` → `done`。
- **遗留去向**：会话累积意图无读端点（一键试卷/互动内容按弹层主题组装 intent）、课件修改回退默认配色主题（`style` 未随版本留痕）、无版本级删除与落盘回收 → 已逐条写入票 14 的派发约束。
