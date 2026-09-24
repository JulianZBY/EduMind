# 11: 冲突三类别

**What to build:** 教师裁决冲突的专属区，三类别分区呈现各自形态：定义冲突 = 新旧知识对照卡片；结构冲突 = 「图谱现状 vs 三种裁决终态」的小型 mermaid 图示，复用图谱区的组件与扁平主题；常识存疑 = 红旗标记 + 原文 + 两选一（照常入库 / 拒绝）+ 编辑修正后入库。存量冲突数据回填为定义冲突。两类新类别的**检测逻辑本体不在本票**，只落数据模型与审核动作。

**Blocked by:** 04 前端基座; 10 知识图谱工作台

**Status:** ready-for-agent

- [x] category 落库，存量冲突数据回填为定义冲突
- [x] 三类别的审核动作 API 行为各有测试
- [x] 常识存疑「编辑修正后入库」落库为修正后内容
- [x] 结构冲突的三个终态图与实际裁决后的图谱变化一致
- [x] 裁决后队列即时更新，终态与三选一 / 两选一动作对应
- [x] README 与面向教师的文案不再承诺未实现的检测类别

## 交付记录

**分支**：`JulianZBY/issue-11-conflict-categories`（本工作树当前分支；未 push、未开 PR、未 merge）
**主提交**：`1b2fa23` · `feat(11): 冲突三类别`（基栈 `0e47f98`，票 10 合入后；未 push、未开 PR、未 merge）
**本行来源**：上面这个哈希在随后的 `docs(11)` 小提交里补上（主提交本身不便写自己的哈希）。

### 一、跑过的命令与结果

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv sync` | 成功（本工作树原先没有 `.venv`） |
| `cd frontend && npm install` | 成功（未新增依赖，`package.json` / `package-lock.json` 无改动） |
| `cd backend && uv run pytest -q` | **263 passed**（基线 249 + 本票新增 14） |
| `cd backend && uv run ruff check .` | `All checks passed!` |
| `cd frontend && npm run gen:api` | 成功：25 条路径 / 28 个操作；`openapi/openapi.json` 与 `src/api/generated/*` 已刷新 |
| `cd frontend && npm run lint` | 通过：`[check:classes] 80 个文件，10 条规则零违规` + oxlint 零告警 |
| `cd frontend && npm run build` | 通过：`check:classes` + `tsc -b` + `vite build`（主包 496 kB；mermaid 仍动态 import 分块） |
| `cd frontend && npm run check:routes` | 通过：七条路由可达（其中 `/conflicts?category=structure` 的断言见「取舍①」） |
| 真机冒烟（临时脚本，见第四节） | 18 项断言全过：真 uvicorn + 真 HTTP，临时库跑完已删净 |
| 前端 jsdom 校验（临时脚本，见第五节） | 37 项断言全过：真 mermaid 解析 + 真渲染四张图（现状 + 三种终态） |

### 二、六个验收项的复现方式

1. **category 落库 + 存量回填为定义冲突**
   - 行为：`uv run pytest tests/test_conflict_categories.py -k backfill -q` ——
     建一个**没有 category 列的旧库**（`conflicts` 表只有 id/user_id/status），跑迁移两遍（验幂等），
     断言补出 `category` / `revised_content` / `review_action` 三列且老行变成 `定义冲突`。
   - 名单与过滤：`-k default_to_definition` —— 新行默认定义冲突，`GET /conflicts?category=` 只回这一类。
   - 迁移本体：`backend/app/db/engine.py` 的 `_LEGACY_COLUMNS` + `_ensure_sqlite_columns()`（补列 + 回填，幂等）。
2. **三类别的审核动作 API 行为各有测试**
   - `uv run pytest tests/test_conflict_categories.py -q`（14 条，全走 HTTP 缝）：定义冲突三选一、
     结构冲突三选一、常识存疑照常入库 / 拒绝、「动作不适用于该类别 = 422 且冲突保持待审」、
     「重复裁决 = 409」「未知冲突 = 404」「未知动作 = 422」。
   - 终态与动作一一对应：定义冲突 / 结构冲突用 `已接受` / `已拒绝` / `并存`；常识存疑用 `已接受` / `已拒绝`。
3. **编辑修正后入库落的是修正后的内容**
   - `-k corrected_content`：POST `{"action":"编辑修正后入库","revised_content":"…"}` ——
     断言图谱节点正文 = 修正后内容、`conflicts.revised_content` = 修正后内容、`new_knowledge.content` = 原文
     （两条都留痕）、响应 `review_action` = `编辑修正后入库`（终态同是 `已接受`，靠它分出是哪条出路）。
4. **三个终态图与实际裁决后的图谱变化一致**
   - `-k structure_outcome_graph`（接受新 / 保留旧 / 并存各一条）：造一条结构冲突（旧知识点带两条邻边、
     新知自带一条 `前置依赖`），先读 `structure_preview` 的对应终态图，再 POST 裁决，
     然后把「图上的节点集合 + 按标题表达的关系集合」与裁决后真实图谱（同类比对）逐项断言相等。
   - 真机确认：真 uvicorn + 真 HTTP 冒烟里 `接受新` 那一步同样比对了终态图与 `GET /knowledge/graph`，并断言旧知识点已被顶替。
5. **裁决后队列即时更新，终态与三选一 / 两选一动作对应**
   - 前端 `src/areas/conflicts/queries.ts`：`useReviewConflict` 成功后 `invalidateQueries({queryKey: conflictKeys.all})`
     ——整类队列作废重取，卡片改用服务端返回的 `status` / `review_action` 呈现（不做乐观删除）。
   - 动作目录是唯一一份：`src/areas/conflicts/actions.ts` 的 `ACTIONS_BY_CATEGORY`（动作 + 终态 + 一句说明），
     卡片按钮下方直接写出「终态 X：……」；临时校验脚本断言这份目录与后端 OpenAPI 的动作枚举完全对得上、
     且三类别的动作→终态映射与 `docs/api/conflicts.md` 的契约一致。
6. **文案不再承诺未实现的检测类别**
   - `rg -n "结构冲突/常识存疑" README.md`：README 第 9 行由「检测『定义冲突/结构冲突/常识存疑』」改成
     「检测**定义冲突**……结构冲突与常识存疑的裁决动作与形态已就位，检测尚未实现（见 ADR-0006）」。
   - 冲突审核区三个分区的常驻说明（`ConflictsArea.tsx` 的 `note`）逐区写明：定义冲突「检测已就位」，
     结构冲突与常识存疑「检测尚未实现（ADR-0006）：这里呈现的是裁决动作与形态」。
   - 文档同步：`docs/api/conflicts.md` 的实现状态段与 `docs/adr/0004` / 新增 `docs/adr/0006`。

### 三、结构冲突图示复用了票 10 的什么

`frontend/src/areas/conflicts/StructureOutcomes.tsx`（不另写渲染），复用入口就是
`frontend/src/components/graph/index.ts` 的三个出口：

| 票 10 的组件 | 本票怎么用 | 传的 props |
| --- | --- | --- |
| `buildFlowchartSource(nodes, edges, options)` | 「服务端小图 → mermaid 源码」的唯一一步（住在 `structureGraph.ts`） | `nodes=[{id, label: title, highlighted: is_new}]`、`edges=[{from, to, relation: relation_type}]`、`options={direction:'LR'}`；新知用 `highlighted` 走 `classDef hit stroke:#ff3366` |
| `FlatMermaid` | 每张图的渲染器（现状 1 张 + 终态 3 张） | `source`（上面的源码）、`label`（“接受新：3 个知识点、3 条关系”）、`errorHint`（面向教师的处置建议）；**没传** `onNodeClick`（终态图是预览，节点不跳转） |
| `RelationLegend` | 小图下方说明四种关系的线型（与画布同源） | 无 props |

`structure_preview` 的 `nodes` / `edges` 字段名与 `GET /knowledge/graph` 一致，是刻意的：两侧能喂同一套画布代码。

### 四、真机冒烟（临时脚本，跑完即删）

脚本放 `%TEMP%\edumind-11-smoke.py`（未入库），`cd backend && uv run python <脚本>`。流程与断言：

1. 临时 `DATABASE_URL` / `VECTORS_DB_PATH` / `UPLOAD_DIR` 下建库；
2. 直插种子数据：旧知识点 + 两条邻边 + 一条结构冲突（新知自带 `前置依赖`）+ 一条常识存疑；
3. 起**真 uvicorn**（:8123，先探端口避免连到旧库）；
4. 真 HTTP：`GET /conflicts?category=结构冲突` → 类别过滤、`category` 字段、`structure_preview` 三终态、现状 = 一跳邻域；
5. 真 HTTP：`接受新` → 200/已接受，且终态图上的知识点与关系集合 = `GET /knowledge/graph` 的真实子图，旧知识点已被顶替；
6. 真 HTTP：常识存疑 `编辑修正后入库` → 200，库里节点正文 = 修正后内容，`revised_content` / `review_action` 留痕；
7. 重复裁决 409、已裁决换动作 409 依旧成立；
8. 新库里定义冲突队列为空（既有链路未被本票改动波及）；
9. 把 `structure_preview` 导出给第五节的前端校验用。

结果：18/18 通过；临时目录（含库文件）已 `rmtree`。踩到的坑记一下：
① 上一次崩溃留下的 uvicorn 还占着端口，第二次跑连到了旧库 → 脚本现在**先探端口**再起服务；
② Windows 上 `proc.send_signal(SIGINT)` 直接抛 `ValueError`，改用 `terminate()`。

### 五、前端复用证据（临时 jsdom 校验，跑完即删）

脚本放 `%TEMP%\edumind-11-frontend-check.mjs` + `%TEMP%\edumind-11-jsdom.mjs`，
`cd frontend && node <脚本>`（用 vite 的 `ssrLoadModule` 加载真实模块，不另抄一份断言）。37 项断言：

- 动作目录 ↔ `openapi/openapi.json` 里 `ReviewRequest.action` 的 6 个取值**双向**相等（无自造、无遗漏）；
- 三类别「动作→终态」映射与契约一致；`asCategory` 的回退口径与后端默认一致；
- 结构冲突四张图（现状 + 三种终态）：源码以 `FLAT_THEME_INIT`（票 10 的常量）打头、
  每个承诺的知识点标题都在源码里、四种关系用第 8 节的线型（`-->` / `==>` / `-.->`）、
  新知才带 `classDef hit stroke:#ff3366`；
- **真 mermaid** 在 jsdom 里 `parse` + `render` 四张图：SVG 里出现每个知识点标题，强调色只出现在有新知的那两张图；
- `queries.ts` 里确实有 `invalidateQueries({queryKey: conflictKeys.all})`，且裁决路径取自生成的 schema。

jsdom 是用 `npm install --no-save jsdom` 临时装的，`package.json` / `package-lock.json` 已从备份还原
（`git diff -- package.json package-lock.json` 为空、`rg jsdom frontend/package-lock.json` 零命中）。

### 六、改动文件

后端：

| 文件 | 改了什么 |
| --- | --- |
| `backend/app/db/models.py` | `Conflict` **末尾追加**三列：`category`（带 `server_default`）、`revised_content`、`review_action`，逐列带中文语义注释 |
| `backend/app/db/engine.py` | `_ensure_sqlite_columns` 改成表驱动的「补列 + 回填」，新增 `_LEGACY_COLUMNS`；回填 `category='定义冲突'` |
| `backend/app/knowledge/conflict.py` | 类别/动作/终态常量表、`ActionNotAllowed`、`resolve_conflict(revised_content=)`、`_rehang_edges`、`_apply_proposed_relations`、`preview_structure`、`_insert_node(content=)`；检测写入 `category="定义冲突"` |
| `backend/app/api/v1/conflicts.py` | 两个端点补 `response_model` 与完整注解（示例覆盖三类别）、`?category=` 过滤、`review_action` / `structure_preview` 字段、422/409/404 口径 |
| `backend/tests/test_conflict_categories.py`（新） | 14 条 HTTP 缝测试 |
| `backend/app/config.py` / `knowledge/graph.py` / `knowledge/pipeline.py` / `knowledge/vector_store.py` / `tests/test_conflict.py` | **仅注释**：悬空引用 `ADR-0001` → `ADR-0006`（见取舍②） |

文档：`README.md`（第 9 行承诺）、`docs/api/conflicts.md`（重写：类别表 / 三选一 / 两选一 + 编辑修正 / 终态图契约 / 前端读法）、
`docs/adr/0004-conflict-categories.md`（加交叉引用）、`docs/adr/0006-conflict-detection-scope.md`（新增）。

前端：`src/api/**`（重新生成）、`src/areas/conflicts/` 下改 `ConflictsArea.tsx` / `queries.ts`，
新增 `actions.ts` / `ConflictCard.tsx` / `ConflictQueuePanel.tsx` / `KnowledgeContrast.tsx` /
`StructureOutcomes.tsx` / `CommonSenseOriginal.tsx` / `structureGraph.ts` / `proposedRelations.ts`；
`src/components/**` **零新增零改动**（复用票 10 的图谱组件）。

### 七、取舍与偏离（都不静默绕过）

1. **动了 `frontend/scripts/check-routes.mjs` 的一行期望**（超出 Ownership 列表，故显式说明）：
   该脚本对 `/conflicts?category=structure` 原来断言空状态标题「没有待审的结构冲突」，
   而本票把队列变成服务端数据后，SSR 渲染停在取数态。断言的意图是「`?category=` 选中了哪个分区」，
   故改为断言该分区自己的文案「正在取「结构冲突」队列」（同样带类别名）。**没有**改任何断言口径的其它部分。
2. **回填与补列写在 `_ensure_sqlite_columns` 里并按需重命名**：与既有 `documents.is_reference` 用同一条幂等迁移路径，
   不引 Alembic（本仓库没有迁移框架，单用户 SQLite）。`bind` 参数只给测试用。
3. **`review_action` 也落库并进列表响应**：常识存疑的「照常入库」与「编辑修正后入库」终态都是 `已接受`，
   只有 `status` 的话，教师日后回看分不出当初走的是哪条出路（`revised_content` 非空虽可推断，但那是靠猜）。
4. **结构冲突的「新知自带关系」用标题表达**（`new_knowledge.relations` 的 `from_title` / `to_title`）：
   知识点 id 在裁决前还不存在，而检测阶段的产物本来就是标题粒度的关系；端点解析不到或自环的关系不入图（不留悬空连线），
   审查中的未知关系类型也一律跳过——与终态图的过滤口径同一套，保证「图上画的 = 真的会发生的」。
5. **终态图是「冲突知识点的一跳邻域诱导子图」**：不进图的关系（端点在邻域外）不画；
   代价是图上看不全「新知还会连到哪些远处知识点」，好处是图上画的每一条都真的会发生。
6. **`preview_structure` 只在「待审的结构冲突」上计算**：已裁决的不再需要预览，其它类别没有邻域语义。
7. **只追加新组件、没动 `components/graph/**` 与 `components/ui/**`**：图谱渲染一行未改，纯复用。

### 八、遗留问题

- **两类检测仍未实现**（本票范围外，ADR-0006 明写）：队列里现在只会出现定义冲突；
  结构冲突 / 常识存疑的检测落地时，只需产出对应 `category`，前端与审核动作不用改。
- **审核区的详情路由仍是占位**（`AreaStub`）：裁决全部在队列卡片里完成，
  `/conflicts/:conflictId` 只保证可寻址；是否要把单条冲突做成独立页面留给后续票。
- **队列不分页 / 不虚拟化**：`GET /conflicts` 一次返回全部类别内冲突（与本仓库其它列表一致）。
- **没有真浏览器验证**：证据是 HTTP 缝测试 + 真机冒烟 + jsdom 真渲染；真机五条主路径冒烟归票 14/08。
- **`data/output` 与开发库不受本票影响**：冒烟与测试全部用临时路径（脚本跑完已删净）。
- 覆盖率提示：`pi-lens` 的 LSP 对 Python 是「静默即干净」，本票的静态证据以 `ruff` + `pytest` 为准。
