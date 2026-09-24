# 12: 题库工作台

**What to build:** 教师的题目资产库：题库查询接口补齐「按考查知识点筛选」（此前只有试卷生成入口，没有查题入口），前端呈现题目列表与题目详情（题型 / 答案 / 来源 / 考查知识点）。试卷自动入库的题目即时可查。

**Blocked by:** 04 前端基座

**Status:** done

- [x] 题库查询接口支持按考查知识点筛选，经 HTTP 缝测试
- [x] 生成试卷入库的题目即时出现在列表
- [x] 题目详情呈现题型 / 答案 / 来源 / 考查知识点
- [x] 列表与详情符合工作台密度与风格自检清单

## 交付记录

**分支**：`JulianZBY/issue-12-question-bank-workbench`（本工作树当前分支；未 push、未开 PR、未 merge）
**主提交**：`c5b6103` · `feat(12): 题库工作台`（12 个文件：后端 3 改 1 增、前端 3 改 2 增、类型快照 3 改、本票 1 改）
**收尾**：本节记录随其后的小提交入库（提交号见 `git log` 顶部）；收尾时 `git status --short` 为空，pi-lens 未留下未提交的格式化改动

### 一、跑过的命令与结果

| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm install` | 成功（本工作树 `node_modules/` 未入库） |
| `cd backend && uv sync` | 成功（`.venv/` 在 `.gitignore` 内，只为跑测试与类型管线） |
| `cd backend && uv run ruff check .` | `All checks passed!` |
| `cd backend && uv run pytest -q` | **193 passed**（既有 185 + 本票新增 8 条 `tests/test_question_bank_api.py`），含 `test_openapi_contract.py` 对「题库」分组的断言 |
| `cd frontend && npm run gen:api` | 成功：**19 条路径 / 19 个操作** → `openapi/openapi.json` + `src/api/generated/{index.ts,types.gen.ts}`（新增 `ListQuestions…` / `GetQuestion…` / `QuestionListResponse` / `QuestionDetail` 等类型） |
| `cd frontend && npm run lint` | 通过：`[check:classes] 禁用 class 扫描通过：59 个文件，10 条规则零违规` + oxlint 零告警，exit 0 |
| `cd frontend && npm run build` | 通过：`check:classes` + `tsc -b` + `vite build`（js 456.88 kB / gzip 145.41 kB），exit 0 |
| `cd frontend && npm run check:routes` | 通过：七条路由可达 + 逐条 SSR 渲染出区名（`/question-bank` 渲染出「题库」），exit 0 |
| stub 全链路真机冒烟（`uv run uvicorn … --port 8123`，`DATABASE_URL`/`VECTORS_DB_PATH`/`UPLOAD_DIR` 指 `%TEMP%`，不污染开发库） | `POST /api/v1/exam/generate` → `bank_saved=3`；紧接 `GET /api/v1/questions` → `total=3`（三道题都在）；`GET /api/v1/questions/{id}` → 200；`GET /api/v1/questions/nope` → `404 {"detail":"题目不存在"}`；`GET /api/v1/questions?knowledge_point=…` → `total=0`；`GET /api/v1/questions?limit=101` → `422` |

### 二、新增接口（票 01 遗留一并收口）

| 端点 | tag | `response_model` | 语义 |
| --- | --- | --- | --- |
| `GET /api/v1/questions` | **题库** | `QuestionListResponse` | 按考查知识点筛选 + 分页；`items / total / limit / offset / knowledge_points` |
| `GET /api/v1/questions/{question_id}` | **题库** | `QuestionDetail` | 题目详情；不存在返回 `404`（不是空对象） |

两个端点都带 `summary`、描述、响应示例与错误码（列表：422 / 500；详情：404 / 422 / 500），tag 用 `CONTEXT.md` 的区名「题库」。

**票 01 登记的遗留**：OpenAPI 的「题库」tag 分组此前缺席（`backend/app/main.py` 里还留着「题库区的查询接口尚未落地，故此处暂无该分组」的注释）。本票在 `TAGS_METADATA` **末尾追加**该分组（带描述），并把 `DESCRIPTION` 的分组导航补成「… / 冲突审核 / 题库」——`tests/test_openapi_contract.py` 的「声明的分组必须都被使用、都有描述」现在成立，且本票另加一条专门断言它（`test_question_bank_group_is_declared_and_used`）。

**接口形状上的四个取舍（都写进 OpenAPI 描述里，前端照此实现）**：

1. **列表不带答案**：`items` 只给题干 / 题型 / 来源 / 考查知识点，答案只在详情外露（工作台密度的列表行不需要泄题）；实现上 `generate/exam.py` 只写一份序列化，列表的响应模型把它裁掉。
2. **筛选项是全量的**：`knowledge_points`（含各自题目数）不随当前筛选收窄——否则教师筛过一次之后就再也换不回别的知识点。
3. **按图谱节点标题筛**：`knowledge_point` 与 `GET /api/v1/knowledge/graph` 的 `title` 一致（教师看到的就是这个标题）。
4. **按入库时间倒序 + 分页上限 100**：试卷刚入库的题目就落在第一页（验收 2），`total` 是筛选后的总数供前端算页数。

### 三、前端界面

- 侧栏（`QuestionList.tsx`，工作台密度）：**按考查知识点筛选**（标签按钮，选中项 = 强调色底；「全部」+ 每个知识点的题目数）→ 题目列表（题型标签 / 来源 / 题干两行截断 / 考查知识点「主考 · 涉及」文案，当前行 = 黑白反色 + 强调色左边线）→ 翻页（上一页 / 第 N / M 页 / 下一页）+ 刷新。
- 主区（`QuestionDetail.tsx`）：题干块 + 数据行 **题型 / 答案 / 来源 / 考查知识点 / 入库时间**；「主考」用实心标签、「涉及」用描边标签；外部来源给「打开来源」按钮。
- **筛选与页码走 URL 搜索参数**（`?knowledge_point=…&page=…`，与冲突审核区同一套做法）：刷新、分享、点进详情再返回都不丢上下文（列表行与「返回题目列表」都带着搜索参数）。
- 服务端状态住 `queries.ts`（TanStack Query，`refetchOnMount: 'always'`：试卷刚入库的题目要立刻可见，不能被 30s 缓存挡住），类型全部取自生成 schema（`ListQuestionsApiV1QuestionsGetData['url']` 之类的 URL 常量也不手抄）。
- 三态齐备：加载中 = 文案 + 直角进度条（无灰块骨架屏）；失败 = 强调色文案「题目列表加载失败 / 题目取不到」+ 重试；空态 = 侧栏「题库还没有题目 / 「X」下还没有题目」+ 主区编辑密度空状态；详情 404 单列成「题目不存在」+ 回到列表，不退化成默认报错样式。

### 四、风格文档第 7 节自检清单

**形状与材质**

- [x] 无 `shadow-*` / `drop-shadow-*`（扫描规则 1 零命中）
- [x] 无 `rounded-*`（除显式 `rounded-none`，容器都写了）（规则 2）
- [x] 无 `bg-gradient-*` / `from-*` / `via-*` / `to-*`（规则 3）
- [x] 无灰度底色（规则 4）与半透明底色（规则 5；`text-black/60` 是文字色深浅，规则只禁 `bg-*`）
- [x] 每个容器用 `border-2 border-black`：筛选区/列表行 `border-b-2 border-black`、进度条外框 `border-2 border-black`、「打开来源」按钮 `border-2 border-black`

**色彩**

- [x] 只有黑、白、`#ff3366`（强调色一律 `bg-[#ff3366]` / `text-[#ff3366]` / `border-[#ff3366]`：选中筛选标签、当前列表行的左边线、失败文案）
- [x] 强调色上没有任何非黑文字（`tone="accent"` 的标签是 `bg-[#ff3366] text-black`）
- [x] 失败状态用强调色 + 明确文案 + 重试按钮，没有红绿蓝

**交互与动效**

- [x] 悬停是黑白反色（列表行 / 筛选标签 / 按钮 / 「打开来源」），无位移、无缩放、无阴影
- [x] 可交互组件覆盖默认 / 悬停 / 聚焦（`focus-visible` + `outline-black`，非浏览器默认蓝圈）/ 禁用四态（列表行与筛选标签复用既有 `Badge`/`Button`/`NavLink` 的四态；翻页按钮的就是 `Button` 的禁用态）
- [x] 过渡只用 `transition-colors duration-150`，无 `transition-all`（规则 7、8）
- [x] 无循环动画；加载态用「文字 + 直角进度条（黑底）」
- [x] 本票无弹层 / 抽屉 / 下拉 / 标签页；筛选用带四态的标签按钮（可键盘操作），不重写无障碍行为

**排版与密度**

- [x] 字体自托管（未新增字体引入，无外链，规则 10 零命中）
- [x] 数字与英文走 Space Grotesk（全局字体栈，题目数 / 页码 / 时间都用它）
- [x] 数据区工作台密度（侧栏行 `px-3 py-2` + 贴边 `border-b-2`；详情一行一字段 `w-24` 标签列）；主区空状态保持编辑密度（`EmptyState`）
- [x] 无 emoji；未新增图标

**图谱**

- [x] 本票不涉及图谱渲染（mermaid 配方属票 10 / 11）

**流程**

- [x] 禁用 class 扫描零违规（已挂 lint / build）
- [x] 空数据 / 加载中 / 失败三态都按本清单实现（见第三节末）

### 五、新增 / 改动文件

**新增（3 个文件）**

- `backend/tests/test_question_bank_api.py` — 8 条 HTTP 缝测试（筛选收窄 / 陌生知识点为空 / 生成后即时可查 / 分页与上限 / 详情四要素 / 详情 404 / 列表不带答案 / OpenAPI 题库分组）
- `frontend/src/areas/question-bank/QuestionList.tsx` — 侧栏：筛选 + 列表 + 分页 + 三态
- `frontend/src/areas/question-bank/QuestionDetail.tsx` — 详情：题干 / 题型 / 答案 / 来源 / 考查知识点 / 入库时间 + 三态

**改动（8 个文件，全部为追加或在既有位置内线内延伸）**

- `backend/app/api/v1/exam.py` — 追加 5 个响应模型、2 个端点、2 段示例常量；import 块只增 `datetime` / `Annotated` / `Query` / `query_question` / `query_questions`（既有导入行末尾延伸，未重排）
- `backend/app/generate/exam.py` — 追加 `query_questions` / `query_question` / `_serialize_questions` / `_knowledge_point_facets`（查询与入库同源，题目一入库即可查）
- `backend/app/main.py` — `TAGS_METADATA` 末尾追加「题库」分组；`DESCRIPTION` 分组导航补「题库」；删掉「题库区查询接口尚未落地」的过期注释
- `backend/app/api/v1/router.py` — **未改**（题库端点与试卷生成同住 `exam.py`，沿用既有 include）
- `frontend/src/areas/question-bank/{QuestionBankArea,queries}.tsx|ts` — 壳改用新侧栏与详情；`queries.ts` 长出列表 / 详情 hooks 与 URL 拼装
- `frontend/openapi/openapi.json`、`frontend/src/api/generated/{index.ts,types.gen.ts}` — `npm run gen:api` 重新生成

**未改**：`docs/**`、`CONTEXT.md`、`backend/app/db/models.py`（**无需补字段**，见遗留 1）、其它 `areas/**`、`src/components/**`（全部复用既有组件，未新增组件文件、未改既有组件视觉）、既有端点路径与既有字段语义、任何 npm 依赖。

### 六、遗留问题

1. **详情不展示「解析」**：`Question` 表只有 `content / answer / type / source_type / source_url`，试卷生成时 prompt 产出的 `analysis` 在 `save_questions_to_bank` 里就没落库（票 07 现状）。本票验收项只要题型/答案/来源/考查知识点，故**没有补字段**——补 `analysis` 需要同时改 `db/models.py` 与 `db/engine.py` 的幂等补列（否则已有开发库会 `no such column`），而 `engine.py` 不在本票 ownership 内，留给后续票。
2. **`knowledge_point` 按标题匹配**：不同章节的同名知识点会被合并成一个筛选项（对教师更直观，但不够精确）；要按 id 精确筛需新增参数，属后续票。
3. **筛选后侧栏仍列全部知识点**（有意）：`knowledge_points` 是全量清单，题目数也是全量题目数，不是「当前筛选命中数」。
4. **没有真浏览器验证**：本票证据是 HTTP 缝测试（TestClient 真发请求）+ `check:routes` 的 SSR 渲染断言 + 真机 uvicorn 冒烟；浏览器逐项点选属票 14 的 Playwright 冒烟范围（本机未装 Playwright 浏览器）。
5. **`openapi.json` 是全量重新生成的**：与并行票 09/10 的快照必然冲突，合并后请重跑 `npm run gen:api` 取并集，不要手工拼 schema。
6. **题目只读**：题库区只做了查询；题目编辑 / 删除 / 按题型与来源筛选都不在本票范围（`questions` 表也没有 `updated_at`）。
7. **列表页容量 20、接口上限 100**：一屏工作台密度的取舍，接口层 `limit>100` 直接 422（已有测试固定该行为）。

## 协调者复核

**结论：通过。** 复核人 = 协调者（主代理），2026-09-24。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| 题库查询按考查知识点筛选 | 新端点 `GET /questions`（筛选 + 分页 + `response_model`），`tests/test_question_bank_api.py` 8 例 HTTP 缝测试 | 通过 |
| 题目详情 | `GET /questions/{question_id}`（含 404 语义、`response_model`） | 通过 |
| 试卷入库题目即时可查 | 真机 uvicorn（临时库）实测：生成试卷 `bank_saved=3` → 立刻 `GET` 列表 `total=3` | 通过 |
| 补齐「题库」OpenAPI 分组（票 01 遗留） | 两处新端点 `tags=["题库"]`，`test_openapi_contract.py` 对已声明分组的断言绿 | 通过 |
| 前端列表与详情密度/风格 | `npm run lint`（59 文件零违规）+ `build` + `check:routes` | 通过 |
| 测试与静态检查 | 协调者亲跑 `uv run pytest -q` → **193 passed**（真基线 185 + 8）、`ruff check .` 干净 | 通过 |

**发现并处置的状态不一致**：pi-lens 收尾格式化又留下 3 个文件未提交（纯折行），协调者逐处核过后代为提交为 `style(12)`，使「合并的状态 = 复核过的状态」。这是本轮第 **3** 个同类实例。

- **合并点**：`aa73ed3`（`merge(12)`）；合并后 main 复跑 → 226 passed + ruff 干净。
- **状态迁移**：`ready-for-agent` → `done`。
- **遗留去向**：① `questions` 表缺 `analysis` 字段（详情不展示解析），补列需同时改 `db/engine.py` 的幂等补列 → 记入票 14 收口清单；② 前端 `openapi.json` 与并行票合并后需重跑 `gen:api` → 已在 main 上重生成（`d925a0d`）；③ 真浏览器点选 → 票 14。
