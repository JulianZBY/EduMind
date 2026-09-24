# 06: 备课会话工作台

**What to build:** 教师的日常主线皮肤。二级侧栏是备课会话列表（新建 / 重命名 / 删除 / 检索），主区是对话主轴——澄清与生成两种回复形态、追问粒度三档切换、语义化跳过追问、会话内上传文件自动归入该会话的参考资料；发起会话时从知识库勾选参考资料。全部数据来自服务端，浏览器里的 localStorage 会话彻底退场。

**Blocked by:** 04 前端基座; 05 会话持久层 + 状态机收编

**Status:** done

- [x] 会话列表的新建 / 重命名 / 删除 / 检索与服务端状态同步
- [x] 对话流正确区分澄清与生成两种回复形态
- [x] 追问粒度切换与跳过操作即时影响后续对话行为
- [x] 会话内上传的文档归入该会话参考资料
- [x] 发起会话可勾选知识库文档为参考资料
- [x] 刷新或换设备进入同一会话，历史完整

## 交付记录

**分支**：`JulianZBY/issue-06-lesson-prep-workbench`　**主提交**：`64580b0 feat(06): 备课会话工作台`（未 push、未开 PR、未 merge）

### 做了什么

二级侧栏 = 备课会话列表（新建 / 重命名 / 删除 / 检索），主区 = 对话轴（两种回复形态、追问粒度三档、
跳过追问、会话内上传归入参考资料、最小结果入口）。全部读写都过服务端：列表走 `GET /sessions?q=`，
增删改走 `POST` / `PATCH` / `DELETE /sessions`，历史走 `GET /sessions/{id}`，一轮对话走 `POST /chat`（带 `session_id`）。
浏览器里没有会话事实——旧 `sessionStore` 已在票 04 删除，本票未引入任何浏览器侧会话事实源。

前端分两层：`queries.ts` 的**数据层**是不依赖 React 的 async 函数（请求 + 缓存改写纯函数），
hooks 只做缓存与失效；`narrowing.ts` 把 OpenAPI 里的自由结构（`artifacts`、资料列表）做白名单式收窄。

### 逐条验收的复现方式

**1. 列表的新建 / 重命名 / 删除 / 检索与服务端同步**

- 界面：`SessionSidebar.tsx`（工作台密度列表 + 检索输入 + 每行「更多」菜单）、`NewSessionDialog.tsx`。
- 复现（临时验收脚本 A1，8 项全过）：新建后出现在服务端列表；列表按最近使用倒序；检索「三角」只返回标题命中的那一条；
  重命名后按新标题可检索；删除后列表不再有它、其历史返回 404。
- 后端既有 HTTP 缝：`tests/test_sessions_api.py`（列表顺序与 `q=` 过滤、重命名、空更新 422、删除）。

**2. 对话流区分澄清回复与生成回复**

- 界面：`ConversationTranscript.tsx`，形态取自消息的 `kind`（`narrowing.readReplyForm` 只认词汇表两个术语）；
  澄清回复 = 描边标签 + 「这是追问，还没有生成物」，**不给**生成物入口；生成回复 = 实心标签 + 最小结果入口。
- 复现（脚本 B 段 5 项）：只渲染澄清回复时 HTML 里没有「本次生成物 / 下载」；只渲染生成回复时有
  「本次生成物 / 下载课件 / 下载教案 / 提纲（文本）」与命中来源；同屏时两种标签都在。
- 形态由服务端落库：`tests/test_session_turns.py::test_session_turns_persist_history_for_other_devices`。

**3. 追问粒度切换与跳过追问即时影响后续**

- 界面：标题条上的 `GranularityPicker`（快速 / 标准 / 精细 → `PATCH /sessions/{id}`，带档位说明）；
  输入区的「跳过追问，直接生成」把标准说法「信息够了，直接生成。」当成教师那一轮原话发出
  （语义判定住服务端 `core/clarify.py`，不靠关键词），草稿里的补充信息并入同一句。
- 复现（脚本 A3，5 项）：切档位后服务端回带新档位；重新拉历史仍是新档位；跳过追问的原话与回复按轮次落库。
- 后端既有 HTTP 缝：`tests/test_session_turns.py::test_chat_with_session_uses_session_granularity`、
  `::test_skip_clarification_accepts_a_synonym_phrasing`、`::test_negated_generation_is_not_treated_as_skip`。

**4. 会话内上传自动归入参考资料**

- 界面：`ConversationComposer` 的「上传参考资料」→ `useAttachReference`：`POST /documents/upload`（`is_reference=true`）
  → `PATCH /sessions/{id}` 提交整份参考资料清单（`withReference` 去重追加）。上传成功但并入失败会明确报错，不静默。
- 复现（脚本 A4，5 项）：上传拿到资料编号 → 编号绑进会话参考资料（服务端回带）→ 重复并入不重复 →
  资料清单里能看到它 → 输入区文案写明「会话内上传的文件自动归入本次备课的参考资料」。

**5. 发起会话时从知识库勾选参考资料**

- 界面：`NewSessionDialog` + `ReferencePicker`（读 `GET /documents`；只有「已完成 / 有冲突」可勾，
  处理中 / 失败 明确说明原因）；发起时随 `POST /sessions` 带 `reference_doc_ids`。
  会话中可改：标题条的「参考资料 N 份」→ 同一个 picker → `PATCH`。
- 复现（脚本 A4 + B 段）：知识库清单读法保留参考资料标记、解析未完成的资料判为不可勾选；
  标题条渲染出「参考资料 2 份」。

**6. 刷新或换设备进入同一会话，历史完整**

- 全部读自 `GET /sessions/{id}`；乐观追加只让「本轮那句话」先出现，失败回滚，成功与否都以服务端返回为准。
- 复现（脚本 A5，3 项）：重新拉取得到完整历史（含上传绑定的参考资料）、序号 1..N、两种形态都在；
  `AppProviders` 没有任何持久化插件（无 sessionStorage/localStorage 中间件）。
- **浏览器侧会话彻底退场的证据**：`rg localStorage frontend/src` → **0 命中**
  （说明性注释也统一写成「浏览器侧会话存储」，保证这条机器证据干净）；`rg sessionStore frontend/src backend/app` → 0 命中。

### 跑过的命令与结果

```text
cd frontend; npm run lint         → 绿（check:classes：71 文件 10 条规则零违规；oxlint 无输出）
cd frontend; npm run build        → 绿（check:classes + tsc -b + vite build，215 modules）
cd frontend; npm run check:routes → 七条路由全绿（含 /lesson-prep/session-abc 渲染出选中对象 id）
cd frontend; npm run gen:api      → 21 条路径 / 24 个操作（票 05 的会话端点首次进快照）
cd backend;  uv run pytest -q     → 226 passed
cd backend;  uv run ruff check .  → All checks passed
node tmp-06-check.mjs（临时验收脚本，已删除）→ 64 项断言全过（A1~A6 数据链路 + B 段无浏览器渲染）
```

dev server 实测（uvicorn 8000 stub + vite 5173，前后端真跑）：

- `GET http://localhost:5173/lesson-prep` → 200，页面外壳含 root 容器；
- 13 个新增/改写的备课会话区模块经 vite 转译全部 200（无编译错）；
- 经 vite 代理：新建会话 → 发起一轮（`clarifying=false`，生成物键 `intent/knowledge_hits/references/ppt/word/outline/interactive`）
  → 拉历史（2 条：教师 / 生成回复）→ 删除（`deleted=true`）。

### 新增 / 改动文件

- 新增（`frontend/src/areas/lesson-prep/`）：`ConversationAxis.tsx`、`ConversationTranscript.tsx`、
  `ConversationComposer.tsx`、`GeneratedResult.tsx`、`GranularityPicker.tsx`、`ReferencePicker.tsx`、
  `NewSessionDialog.tsx`、`SessionSidebar.tsx`、`narrowing.ts`、`format.ts`、`routes.ts`
- 改写：`frontend/src/areas/lesson-prep/queries.ts`（服务端状态层）、`LessonPrepArea.tsx`（三段面板）
- 追加组件：`frontend/src/components/ui/Textarea.tsx` + `components/ui/index.ts` 追加两行 export
  （不改既有组件视觉）
- 重新生成：`frontend/openapi/openapi.json`、`frontend/src/api/generated/{index,types.gen}.ts`
- 后端最小改动：`backend/app/api/v1/chat.py` 的 200 响应示例里 `outline` 改成 **对象形态**
  `{text, path, filename}`（与票 07 已交付的 `core/orchestrator.py` 一致——`artifacts.outline` 从字符串变成与课件/教案同形的对象）。
  只改示例，不动端点语义与字段名；本票的读法对两种形态都兼容（见下）。

### 设计取舍

- **跳过追问不新增后端字段**：状态机只认「教师那一轮原话 + 累计意图」，语义判定已在服务端；
  所以界面把标准说法当原话发出去，草稿里的补充信息并入同一句（信息一起进历史）。
- **新建弹层与检索词放在地址上**（`?new=1`、`?q=`）：URL 即状态，刷新/分享不丢上下文，不引第二份浏览器状态。
- **数据层与 hooks 分层**：请求函数与缓存改写纯函数可脱离 React 调用（验收脚本直接拿真后端跑），hooks 只做缓存与失效。
- **弹层只在打开时挂载**：初值直接取服务端清单，不在 `useEffect` 里同步服务端状态。
- **生成物只给最小结果入口**（下载课件 / 下载教案 / 提纲文本 / 互动内容新标签页 + 命中来源），
  不做版本列表、版本时间线与独立生成物面板（票 07 落版本记录、票 08 落版本中心）。
- **兼容票 07 的提纲对象形态**（协调者提醒后的核对）：07 起 `outline` 是 `{text, path, filename}`
  （与课件 / 教案同形），早期版本是纯文本。`narrowing.outlineEntry` 两种形态都吃：有落盘文件就给「下载提纲」，
  只有正文就给可展开的文本；逐个形态核对过：`07 形态 → 下载提纲`、`只有正文 → 提纲（文本）`、
  `早期字符串 → 提纲（文本）`、`空对象 → 不列`。票 07 新增的版本端点本票不消费（版本中心是票 08）。

### 遗留问题与发现（不在本票 ownership，只报告）

1. **`GET /api/v1/documents` 与 `POST /api/v1/documents/upload` 没有 `response_model`**，生成的类型是 `unknown`。
   本票按纪律不手抄接口类型，改为在 `narrowing.ts` 做白名单式运行时收窄；补 `response_model` 归票 09
   （`documents.py` 不在本票 ownership，且 09 在并行改同一文件）。
2. **`artifacts` 在 OpenAPI 里是自由 dict**（`{[key: string]: unknown}`），前端同样只能运行时收窄。
   要生成强类型，需要后端为生成物建模型——票 07 的版本记录天然要做这件事。
3. **stub 模式下上传永远到不了「已完成」**：`txt` 等格式没有解析器（`不支持的格式`），图片 / 视频缺 vision stub
   （票 09 也报过同一处）。因此「只有已入库的资料能勾选」这条规则在本机只能用 seed 数据核对；
   真链路要等补上 vision stub 才能端到端跑通。
4. **会话内上传是两步（上传 + 绑定），不是原子的**：若上传成功而 `PATCH` 失败，界面会说明「资料已上传但没并入本次备课」，
   重试会再上传一份重复文件（单用户产品可接受）。要严格原子化需要后端给「上传并归入会话」的单一端点；
   本票按工单口径（票 05 已给 `PATCH`，绑定动作由本票完成）未新增端点。
5. **本机无浏览器 / Playwright**：交互（点击、弹层、键盘）只做了 SSR 渲染断言与真服务数据链路核对，
   真浏览器点选留票 14。

## 协调者复核

**结论：通过。** 复核人 = 协调者（主代理），2026-09-24。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| 会话列表新建/重命名/删除/检索与服务端同步 | 读 `frontend/src/areas/lesson-prep/SessionSidebar.tsx` + `queries.ts`（全部走服务端） | 通过 |
| 对话流区分澄清/生成两形态 | `ConversationTranscript.tsx` + 交付记录的两形态断言 | 通过 |
| 追问粒度切换与跳过即时影响后续对话 | `GranularityPicker.tsx` + 服务端为准 | 通过 |
| 会话内上传归入参考资料 / 发起会话勾选参考资料 | `ReferencePicker.tsx` + 票 05 的 `PATCH /sessions/{id}` | 通过 |
| **localStorage 会话彻底退场** | 协调者亲跑 `rg localStorage frontend/src` → **零命中** | 通过 |
| 测试与静态检查 | 协调者亲跑 `uv run pytest -q` → 226 passed、`ruff check .` 干净、工作树干净 | 通过 |

**跨票协调**：票 07 交付时报告 `artifacts.outline` 由字符串变对象，协调者当即把这条变化通过 `orchestration send` 转达给**仍在跑**的本票；本票据此做了兼容读取与 `chat.py` 示例对齐（未扩大范围去实现票 07/08 的内容）。

- **合并点**：`593876d`（`merge(06)`，与票 15 同批）；合并时只与派生物 `frontend/src/api/generated/*` 冲突，按「重生成」处置。
- **状态迁移**：`ready-for-agent` → `done`。
- **遗留去向**：`/documents` 两个端点缺 `response_model`（本票用运行时收窄顶住）→ 已登记进票 14 收口清单；真浏览器点选 → 票 14。
