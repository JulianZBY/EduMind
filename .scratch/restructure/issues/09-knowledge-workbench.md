# 09: 知识库工作台

**What to build:** 教师管理教学资料的专区：上传 PDF / Word / PPT / 图片 / 视频 / 录音，文档列表带解析状态自动跟进（处理中 → 已完成 / 失败），参考资料标记即时切换，文档详情页。

**Blocked by:** 04 前端基座

**Status:** done

- [x] 上传后解析状态自动跟进到终态（处理中 → 已完成 / 失败），无需手动刷新
- [x] 参考资料标记切换即时生效
- [x] 空状态与错误态符合编辑密度与风格自检清单
- [x] 文档数据走服务端状态缓存，重复进入不重拉

## 交付记录

**分支**：`JulianZBY/issue-09-knowledge-workbench`（本工作树当前分支；未 push、未开 PR、未 merge）
**主提交**：`7b4f7d4` · `feat(09): 知识库工作台`
**收尾提交**：本节的勾选与记录（`docs(09): 勾选验收项 + 交付记录`）。

### 一、跑过的命令与结果

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv sync` | 成功（本工作树原先无 `.venv`；`.venv` 在 `.gitignore` 内） |
| `cd frontend && npm install` | 成功：178 个包，未新增/升级任何依赖 |
| `uv run ruff check .` | 通过：`All checks passed!` |
| `uv run pytest -q` | 通过：**193 passed**（基线 185 + 本票新增 8 条），含 `tests/test_openapi_contract.py` 全项 |
| `uv run pytest tests/test_documents_workbench.py -q` | 通过：8 passed（本票新增的 HTTP 缝测试） |
| `npm run lint` | 通过：`[check:classes] 63 个文件，10 条规则零违规` + oxlint 零告警 |
| `npm run build` | 通过：`check:classes` + `tsc -b`（无错）+ `vite build`（js 464.04 kB / gzip 147.58 kB，css 19.59 kB） |
| `npm run gen:api` | 成功：**19 条路径 / 19 个操作**（原 16 条；新增本票 2 个端点 + 基线里已有但快照漏掉的 `/knowledge/retrieve`）。连跑两次哈希一致 → **幂等** |
| `npm run check:routes` | 通过：七条路由可达 + 逐条 SSR 渲染 + 默认路由 = 备课会话 |
| 真服务实测（uvicorn 8000 + vite 5199） | 见第三、四节：上传 → 终态、标记切换、404/422、SPA 子路由，逐条打印了实测输出 |
| 临时 SSR 断言脚本（`frontend/check-knowledge-ui.tmp.mjs`，**跑完即删、不入库**） | **27 项断言全过**：轮询口径 6 项 + 乐观改写/回滚 4 项 + 真组件渲染 17 项 |

### 二、后端接口（本票新增 2 个、补齐 2 个的 `response_model`）

| 方法 · 路径 | 状态 | 说明 |
| --- | --- | --- |
| `POST /api/v1/documents/upload` | 改动 | 路径与字段语义不变；补 `response_model=DocumentView`（原来 200 是 `{}`，前端类型是 `unknown`） |
| `GET /api/v1/documents` | 改动 | 同上，补 `response_model=DocumentListResponse`；响应形状与字段一字未改 |
| `GET /api/v1/documents/{document_id}` | **新增** | 资料详情：状态、参考资料标记、解析完成时间、待审冲突数、分块明细（前 200 个 + 全量 `chunk_count`）；404 = 资料不存在 |
| `PATCH /api/v1/documents/{document_id}/reference` | **新增** | 切换参考资料标记。请求体给**目标值**（`{"is_reference": true}`）而非翻转，重复提交幂等；404 = 资料不存在，422 = 缺字段 |

接口纪律：两个新端点都带 `summary` / 描述 / 请求响应示例 / 错误码 / `tag="知识库"`；`status` 字段在后端写成
`Literal["处理中","已完成","有冲突","失败"]`，因此生成的 TS 类型是**联合类型**（前端判断终态不必猜字符串）。
详情里的分块读取走 `VectorStore.list_doc_chunks()`（知识引擎的只读入口，本票只加这一个方法），
路由层不含业务逻辑——与既有 `POST /knowledge/search` 直接在路由里用 `VectorStore()` 的写法一致。

**没动的东西**（并行协作纪律）：`router.py` 一行未改（新端点挂在既有 `documents_router` 上，不需要追加 include）、
`db/models.py` 一行未改（无新表/新字段）、`frontend/src/components/**` 一行未改
（新界面全部住在 `areas/knowledge/`，没有改动任何既有组件的视觉）。

### 三、验收项 1：解析状态自动跟进到终态（无需手动刷新）

**契约**：上传**立即**返回 `status=处理中`；之后 `GET /documents` 与 `GET /documents/{id}` 报当前状态，
后台解析结束即落终态 `已完成` / `有冲突` / `失败`（CONTEXT.md 第 4 节状态口径）。
**前端**：

- 列表：`refetchInterval: hasProcessing(documents) ? 1500 : false`——只要列表里还有一份「处理中」就每 1.5 秒拉一次，
  全部落终态**自动停**（`frontend/src/areas/knowledge/queries.ts`，判定口径落在纯函数 `hasProcessing` / `isProcessing` 里，单点可查）；
- 详情：同一个策略，条件是这份资料的状态；
- 上传成功即 `invalidateQueries(['knowledge'])`，列表立刻出现新资料（`处理中`），随后由轮询接手；
- **界面上没有「刷新」按钮**——跟进不依赖任何手动动作。

**证据 A（HTTP 缝，自动）**：

```bash
cd backend && uv run pytest tests/test_documents_workbench.py -q    # 8 passed
```

| 测试 | 断言的是响应与数据变迁 |
| --- | --- |
| `test_upload_returns_processing_then_reaches_completed_without_manual_refresh` | 上传响应 `处理中` → 再读同一份资料 = `已完成`（stub 录音转写 → 分块入库） |
| `test_processing_document_is_visible_in_list_and_detail` | 解析未结束时列表与详情都如实报 `处理中`，`parsed_at` 为空、分块为空（**这就是前端轮询要观察的形态**） |
| `test_parse_failure_is_reported_as_terminal_state_and_keeps_no_chunks` | 损坏 PDF → `失败` 终态，且不留任何分块 |

**证据 B（真服务实测，uvicorn 8000 + vite 5199，stub 模式无任何云端 Key）**：

```powershell
# 起后端（隔离到临时 data 目录，不污染开发库）
cd backend; uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
# 起前端（vite 代理 /api → 8000）
cd frontend; npm run dev -- --port 5199 --strictPort
# 经 vite 代理上传（curl 发原始 UTF-8 文件名，与浏览器一致）
curl.exe -s -X POST http://localhost:5199/api/v1/documents/upload -F "file=@课堂录音-一次函数.mp3;type=audio/mpeg" -F "is_reference=false"
```

实测输出（原样摘录）：

```
上传响应: {"id":"31742747-...","filename":"课堂录音-一次函数.mp3","file_type":"mp3","status":"处理中","is_reference":false}
紧随其后的轮询: 62ms=已完成
详情: status=已完成 chunk_count=1 returned=1 parsed_at=09/24/2026 19:00:26 filename=课堂录音-一次函数.mp3 file_type=mp3
失败资料的详情: status=失败 parsed_at= chunk_count=0 chunks=0
```

即：**上传那一刻是「处理中」，下一次读（62 ms 后、没有任何手动动作）就是「已完成」**；损坏文件同样是终态「失败」。

**证据 C（界面层，临时 SSR 断言脚本）**：用与 `scripts/check-routes.mjs` 同样的做法（`vite.ssrLoadModule` 加载真源码 +
`react-dom/server` 渲染真组件 + 预热 QueryClient 提供数据态）逐条断言：

```
（27 项断言的摘要：轮询口径 6 + 乐观改写/回滚 4 + 真组件渲染 17；部分行是多条合并）
✓ 全是终态 → 停止轮询            ✓ 有「处理中」→ 继续轮询
✓ 空列表 / 未加载 → 不轮询        ✓ isProcessing 只认「处理中」
✓ 侧栏逐条渲染资料文件名          ✓ 侧栏显示解析状态（处理中 / 有冲突）
✓ 侧栏计数带「处理中」            ✓ 未选中 → 编辑密度空状态
✓ 空库 → 空状态 + 上传入口        ✓ 错误态 → 强调色错误块 + 重试（未退回默认样式）
✓ 详情（处理中）：说明会自动跟进到终态，分块区给出等待说明
✓ 详情（已完成）：状态说明 + 分块按次序列出且带可回溯编号 + 正文原样呈现
✓ 详情（失败）：给「重新上传」的出路   ✓ 详情（有冲突）：指出裁决去处（链接 /conflicts）
```

（脚本是临时的、**未入库**：它在 `frontend/` 根下、不在本票 ownership 内；断言清单如上，可照抄重建。
一个坑记在这：React Query v5 在服务端渲染时对**没有数据**的查询一律报 pending，所以错误态那一条要先往缓存里塞一份数据、
再让请求失败，才能渲染出错误分支。）

**手动复现（最短路径）**：`/knowledge` → 右上角「上传资料」→ 选一个 mp3/wav 等录音或一张真实 PDF →
上传后弹层立刻关闭并出现轻提示；左列马上多出一行，状态会自己从「处理中」变成「已完成」/「失败」，
**全程不点任何刷新**。

### 四、验收项 2：参考资料标记切换即时生效

- 后端：`PATCH /documents/{id}/reference` 给目标值（幂等），响应即最新状态；
- 前端：`onMutate` 里 `applyReferenceOptimistically()` **先按目标值改写列表与详情两个缓存**（点下去立刻变，不等接口），
  接口失败由 `rollbackReference()` 把两个缓存一起退回切换前的快照并弹强调色轻提示；
  接口回话后 `invalidateQueries` 与服务器校准（`frontend/src/areas/knowledge/queries.ts`）。

**证据 A（HTTP 缝）**：`test_reference_mark_toggle_takes_effect_immediately`——切换响应、列表、详情三处口径一致；
`test_reference_mark_toggle_rejects_unknown_document_and_bad_body`——404 / 422。
**证据 B（真服务实测）**：

```
PATCH true  -> {"id":"31742747-...","status":"已完成","is_reference":true}
列表随即读到 -> is_reference=True
PATCH false -> {..."is_reference":false}
列表随即读到 -> is_reference=False
未知 id -> HTTP 404 {"detail":"资料不存在: nope"}      缺字段 -> HTTP 422
```

**证据 C（乐观改写/回滚，临时脚本 4 项）**：点下去列表缓存立刻变 / 详情缓存立刻变 / 接口失败两处一起回滚 /
未预热的缓存不会被凭空创建。
**手动复现**：左列任意一行的「参考资料」按钮或详情页的「标记为参考资料」——**按下即变色**（强调色底 = 已标记），
刷新后仍是新状态；在 `/conflicts`、`/lesson-prep` 之间来回切也不丢。

### 五、验收项 3：空状态 / 错误态（编辑密度）与风格自检清单

**四态都走编辑密度**（`EmptyState`：`max-w-md` 单列窄容器、`py-12` 大留白、`text-xl` 标题、一屏只做一件事）：

| 状态 | 主区表现 |
| --- | --- |
| 加载中 | 文案「正在读取资料列表…」（无骨架屏灰块；详情同） |
| 空库 | 「还没有教学资料」+ 强调色按钮「上传资料」 |
| 未选中 | 「还没有选中教学资料」+ meta「N 份资料，其中 M 份处理中」 |
| 读不出来 | 「资料列表没有读出来」+ 说明 + 强调色「重试」（不退化成默认样式） |
| 详情读不出来 | 「这份资料读不出来」+「重试」 |

侧栏（工作台密度）另有紧凑版说明（`SidebarNote`）：读取中 / 未读出 / 空库 / 计数「N 份资料 · M 份处理中」。

**风格文档第 7 节自检清单（逐项）**

*形状与材质*

- [x] 无 `shadow-*` / `drop-shadow-*`；无 `rounded-*`（除显式 `rounded-none`）
- [x] 无渐变、无灰度底色、无半透明底色（扫描规则 3/4/5 零命中）
- [x] 每个容器都是 `border-2 border-black` + `rounded-none`（分隔一律 `border-b-2 border-black`，无 1px 淡线）

*色彩*

- [x] 只有黑、白、`#ff3366`（强调色一律写 `bg-[#ff3366]` / `border-l-[#ff3366]`，可一次 grep 出全部使用点）
- [x] 强调色上没有非黑文字（accent 档按钮/标签一律 `text-black`）
- [x] 成功 / 失败 / 警告不用红绿蓝：「有冲突」「失败」= 强调色标签 + 直角方块图标 + 明确文案；
      状态块左侧 8px 条只在需要教师处理时转强调色

*交互与动效*

- [x] 悬停黑白反色（列表行 `hover:bg-black hover:text-white`、按钮/标签/链接同），无位移、无缩放、无阴影
- [x] 四态齐全：按钮/标签/链接/文件选择都有默认 / 悬停 / `focus-visible:outline-2 outline-offset-2 outline-black` / 禁用
      （`sr-only` 的原生 file input 靠外层 `focus-within` 显示聚焦）；参考资料按钮带 `aria-pressed`
- [x] 过渡只用 `transition-colors duration-150`；无循环动画（「处理中」的进度条是静态不跑动的直角条，
      因为后端没有真实进度可报，不做假动画）
- [x] 弹层用 Radix Dialog（Esc / 焦点陷阱 / 键盘可达由原语承担），面板 `border-2 border-black`、遮罩不透明不模糊

*排版与密度*

- [x] 字体自托管（沿用基座，无外链 CDN）；数字与英文走 Space Grotesk（`uppercase` 的文件类型、分块编号）
- [x] 数据区工作台密度（列表行 `px-3 py-2`、贴边 `border-b-2`、键值一行排开）；空状态 / 错误态 / 上传弹层编辑密度
- [x] 无 emoji；图标沿用统一线宽 2 的线性 SVG（`MarkerIcon`，直角方块）

*图谱* — 不适用（本票不碰图谱区）。

*流程*

- [x] 禁用 class 扫描零违规（已挂进 `npm run lint` 与 `npm run build`：63 个文件 / 10 条规则）
- [x] 空数据、加载中、失败三态都过本清单（见上表；失败态用强调色边框 + 文案 + 图标 + 出路按钮）

### 六、验收项 4：服务端状态缓存（重复进入不重拉）

- 资料数据全部走 TanStack Query：`knowledgeKeys.list()` 与 `knowledgeKeys.detail(id)`，hooks 只住本区 `queries.ts`；
- `staleTime: 30_000`（与全局默认一致并显式写出）：30 秒内从列表进详情、再退回列表，直接命中缓存，**不发请求**；
- 只有两种情况下会重新拉：解析中的轮询、以及上传/切换标记后的 `invalidateQueries` 校准；
- 详情与列表共用一个 QueryClient（`src/app/providers.tsx` 的全局实例），所以进详情页时若列表刚拉过，切换标记的乐观改写会同时作用在两处。
- 复现：打开浏览器 DevTools Network，`/knowledge` → 点一份资料 → 点返回资料列表 → 再点进同一份，
  第二次进入不会出现新的 `/api/v1/documents/{id}` 请求（30 秒窗口内）。

### 七、新增 / 改动文件清单

**后端（新增 1，改动 2）**

- 新增 `backend/tests/test_documents_workbench.py`（8 条 HTTP 缝测试：终态跟进 / 处理中形态 / 失败形态 / 详情与分块 / 标记切换 / 404 / 422 / 响应同形）
- 改动 `backend/app/api/v1/documents.py`：+2 个端点（详情、参考资料标记）、+5 个模型（`DocumentView` / `DocumentListResponse` / `DocumentChunk` / `DocumentDetail` / `ReferenceRequest`）、给上传与列表补 `response_model`；**既有端点的路径与字段语义一字未改**
- 改动 `backend/app/knowledge/vector_store.py`：+`list_doc_chunks()`（详情页的只读入口，纯新增方法）

**前端（新增 6，改动 2 + 生成物 3）**

- 新增 `frontend/src/areas/knowledge/status.ts`（状态口径：联合类型、`isProcessing` / `hasProcessing`、状态文案与档位）
- 新增 `frontend/src/areas/knowledge/store.ts`（本区界面状态：上传弹层开合，三个入口共用一个弹层）
- 新增 `frontend/src/areas/knowledge/DocumentStatus.tsx`（状态标签组件）
- 新增 `frontend/src/areas/knowledge/DocumentList.tsx`（侧栏资料列表 + 行内参考资料切换）
- 新增 `frontend/src/areas/knowledge/UploadDialog.tsx`（上传弹层：选文件 + 参考资料标记）
- 新增 `frontend/src/areas/knowledge/DocumentDetail.tsx`（详情页：状态块 / 解析事实 / 分块明细）
- 改动 `frontend/src/areas/knowledge/KnowledgeArea.tsx`（区外壳 + 列表四态 + 详情路由组件；仍导出 `KnowledgeArea` / `KnowledgeIndex` / `KnowledgeDocument`，`index.tsx` 未动）
- 改动 `frontend/src/areas/knowledge/queries.ts`（服务端状态：列表 / 详情轮询、上传、参考资料标记 + 乐观改写/回滚）
- 生成物 `frontend/openapi/openapi.json`、`frontend/src/api/generated/{index.ts,types.gen.ts}`（`npm run gen:api` 重新生成）

**未改**：`backend/app/api/v1/router.py`、`backend/app/db/models.py`、`frontend/src/components/**`、`frontend/src/areas/` 下其它区、
`frontend/package.json`（未加依赖、未加脚本）、`docs/**`、`CONTEXT.md`、其它票的 `.scratch/**` 文件。

### 八、遗留问题

1. **图片 / 视频在无云端 Key（stub）时必然落「失败」**：`LLMProvider.vision` 没有 stub 实现
   （`backend/app/core/llm/base.py:34` 抛 `NotImplementedError`，`core/llm/providers/stub.py` 只实现了 `chat`）。
   实测：`板书照片.png` / `课堂实录.mp4` 上传后都是 `处理中 → 失败`（`讲义.docx` / `讲义.pdf` 只是因为我喂的是假字节才失败；
   真实 docx/pdf 走本地解析没有问题，`课堂录音.mp3` 走 stub 转写 → `已完成`）。这不在本票 ownership（`core/llm/**`）内，
   所以只报告未改：建议给 `StubProvider` 加一个打标记的 `vision`（返回「[stub 图片解读] …」之类），
   否则 stub 模式下「上传图片/视频」这条主路径只能看到失败。
2. **上传不做格式校验**：扩展名不在解析器注册表里的文件会落「失败」而不是被上传时拒掉（前端 `accept` 只做选择器过滤）。
   详情页对失败资料只给「解析没有成功，请按原文重新上传」，**不回显失败原因**（真实原因只在后端日志里）——
   若要给教师看原因，需要后端把失败原因落库（新字段，属别的票）。
3. **非浏览器客户端的文件名编码**：用 PowerShell `-Form` 上传中文文件名时，文件名以 RFC 2047 编码到达
   （`=?utf-8?B?...?=`），`file_type` 因此为空 → 落「失败」。curl 与浏览器发的是原始 UTF-8，中文文件名实测正常
   （`课堂录音-一次函数.mp3` 原样回显、正常解析）。若要兼容这类客户端，需在后端做文件名归一（不在本票范围）。
4. **列表无分页**：`GET /documents` 全量返回（单用户产品，资料量小）；资料多了要加分页，前端轮询也要跟着只取状态。
5. **详情只回前 200 个分块**（`chunk_count` 是全量，页面会写明「共 N 个，这里显示前 200 个」）；要看全量得加分页参数。
6. **没有真浏览器验证**：本票证据是 HTTP 缝测试 + 真服务（vite 代理）实测 + SSR 渲染断言；
   真浏览器点按（上传、切换标记）留给票 14 的 Playwright 冒烟。
7. **文档未同步**：`docs/**` 本票冻结，所以 `docs/architecture.md` 里「知识库…（票 09 补详情与状态跟进）」
   与 `docs/api/` 的端点清单还没有改成「已交付」；本票新增的 2 个端点已进 OpenAPI 快照（`frontend/openapi/openapi.json`），
   收敛时一并更新文档。

## 协调者复核

**结论：通过（含一次生成产物冲突处置）。** 复核人 = 协调者（主代理），2026-09-24。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| 上传后解析状态自动跟进到终态 | 新端点 `GET /documents/{document_id}` + `PATCH /documents/{document_id}/reference` 带 `response_model` / 示例 / 「知识库」tag；`tests/test_documents_workbench.py` 8 例 HTTP 缝测试 | 通过 |
| 参考资料标记即时切换 | 前端乐观改写 + 失败回滚；HTTP 缝测试覆盖切换与 404 | 通过 |
| 空状态/错误态密度与风格清单 | `npm run lint`（65 文件零违规）+ 交付记录自检清单 | 通过 |
| 服务端状态缓存、重复进入不重拉 | 列表/详情走 TanStack Query，状态轮询到终态自动停 | 通过 |
| 测试与静态检查 | 协调者亲跑 `uv run pytest -q` → **193 passed**（真基线 `9468fc0` 185 + 8）、`ruff check .` 干净；工作树干净 | 通过 |

**合并冲突处置（协调者）**：本票与并行票 12 都全量重生成过 `frontend/openapi/openapi.json` 与 `src/api/generated/*`，合并时 3 个文件冲突。按「**派生文件任取一侧 + 在合并后的后端上重新生成**」处置：合并 `25a4de1`，随后在 main 上 `npm install` + `npm run gen:api` 重生成（`d925a0d`），快照同时含 documents 与 questions 两组端点，`npm run build` / `npm run lint` 通过。
> 附带修掉一处环境问题：main 的 `frontend/node_modules` 是票 04 之前的旧依赖，导致 `gen:api` 与 `build` 报 `openapi-ts` 不存在、`@tailwindcss/vite` 找不到、`src/store/ui.ts` 两个 TS7006 —— 全部是旧依赖所致，`npm install` 后消失。

- **合并点**：`25a4de1`（`merge(09)`）+ `d925a0d`（派生物重生成）。
- **状态迁移**：`ready-for-agent` → `done`。
- **遗留去向**：① **stub 模式图片/视频必然失败（缺 vision stub）→ 已建票 15 并派 worker**（违反 ADR-0003「必有 stub」，且卡票 14 的多模态冒烟）；② 列表无分页、详情只回前 200 个分块 → 记入票 14 收口清单。
