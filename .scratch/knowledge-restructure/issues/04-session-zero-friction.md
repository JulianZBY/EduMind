# 04: 新建备课会话零表单直开

**What to build:** 教师点「新建备课会话」**立即**进入一个新会话开始说话：不弹窗、不勾资料、
不选粒度。会话先叫「未命名备课」，教师发出首条消息后自动以消息内容命名；教师手动改过名，
之后不再自动改。改名入口常驻。参考资料改为备课过程中随时挂/换（会话内已有该能力，保留）。

**Blocked by:** None (can start immediately)

**Status:** done

- [x] `NewSessionDialog` 与 `ReferencePicker` 从新建流程退场：点「新建备课会话」→
  `POST /api/v1/sessions` → 导航到 `/lesson-prep/{id}`，全程无弹层
  （`?new=1` 的 URL 状态机制一并清理或改造，不留死链）
- [x] 后端支持「未命名备课」初始态与自动命名：首条教师消息后自动以消息内容命名；
  教师手动改名后自动命名停用（需要最小 schema 标记，如 `title_edited`；落库带中文语义注释）
- [x] 改名入口：会话头/侧栏可inline改名（走既有 `PATCH /sessions/{id}`）
- [x] 追问粒度默认「标准」，会话内 `GranularityPicker` 照旧可改（弹窗里的粒度选择随弹窗消失）
- [x] 词汇表口径：「未命名备课」「备课会话」照 CONTEXT.md §2 用词
- [x] 离线测试：创建即开、首条消息自动命名、手动改名后不再自动覆盖 三态
- [x] `uv run pytest -q`、`npm run lint`、`npm run build`、`npm run check:routes` 全绿

【Ownership】
- 可改：`frontend/src/areas/lesson-prep/`（`NewSessionDialog.tsx`、`SessionSidebar.tsx`、
  `ConversationAxis.tsx`、queries）、`backend/app/api/v1/sessions.py`、`app/core/session_service.py`、
  `app/db/`（sessions 表）、`backend/tests/`
- 禁区：生成物区与生成流程；`ReferencePicker` 若被会话内挂资料复用则保留组件本体、只退新建流程

【约束】前端视觉过 `docs/style/minimalist-flat.md` 自检清单（零阴影/零渐变/border-2 border-black/
rounded-none/hover 反色）；文案中文全角标点。

## 交付记录（2026-10-08，lane W04）

- **分支**：`pi-subagents/t04-d2a7caa-a75e-s0-t0`
- **Commit**：`16afdc4` feat(lesson-prep): 新建备课会话零表单直开 + 未命名备课自动命名（票 04）；
  后续收编 `b167649` style(backend)（pi-lens 空行规范化）与本票交付记录（即本提交）
- **命令与结果**：
  - `cd backend && uv run pytest -q` → **394 passed**（含新增命名三态测试）
  - `cd backend && uv run ruff check .` → 145 个 `EXE002`（本 worktree 是 fuse 挂载点，
    全部文件被强制 0777，属环境性噪音；未触碰的既有文件同样命中）；
    `--ignore EXE002` 后**全仓通过**，改动文件零其它违规
  - `npm run lint` → 通过（含禁用 class 扫描：109 文件 10 规则零违规）
  - `npm run build` → 通过（tsc + vite；chunk 体积警告为既有现象）
  - `npm run check:routes` → 七条路由全部可达，默认路由 = 备课会话
  - `npm run gen:api` → OpenAPI 快照与 TS 类型已随 `title_edited` 同步刷新
  - 项目钉住的 pyright（`backend/` 下，[tool.pyright] venv）对本票改动文件 0 错误
- **新建文件**：`frontend/src/areas/lesson-prep/SessionRenameForm.tsx`（会话头/侧栏共用的 inline 改名表单）
- **删除文件**：`frontend/src/areas/lesson-prep/NewSessionDialog.tsx`
- **改动文件**：
  - 后端：`app/db/models.py`（`title_edited` 列 + 中文语义注释）、`app/db/sessions.py`（update 接受标记）、
    `app/db/engine.py`（幂等补列 + 旧占位标题回填「未命名备课」）、`app/core/session_service.py`
    （初始名改「未命名备课」、首条消息自动命名守卫、改名落标记）、`app/api/v1/sessions.py`
    （`SessionSummary.title_edited` + 示例与描述更新）、`tests/test_sessions_api.py`、`tests/test_session_turns.py`
  - 前端：`SessionSidebar.tsx`（新建直达 + 行内改名 + 清 `?new`）、`LessonPrepArea.tsx`（空状态新建直达）、
    `ConversationAxis.tsx`（会话头 inline 改名 + 404 态新建直达）、`queries.ts`（`useCreateAndOpenSession`）、
    `openapi/openapi.json`、`src/api/generated/types.gen.ts`（gen:api 产物）
- **实现要点**：
  - 自动命名守卫为「未改名且仍叫初始名」（`not title_edited and title == 未命名备课`）：
    手动改名锁存；首轮失败回滚后下一轮仍可自动命名；创建时显式传 `title` 的调用方不自动覆盖（旧契约不变）
  - 只改粒度/参考资料不算手动改名（`title_edited` 不误置，有测试钉住）
  - `ReferencePicker` 组件本体保留（会话内挂资料的 `ReferencesDialog` 仍用），仅退新建流程
- **遗留问题**：
  1. `docs/acceptance-manual.md` 手册第 78 行仍描述旧弹层流程（「不填标题直接确认」）——docs/ 不在本票
     Ownership，留协调者派文档收口
  2. 编辑时自动检查（lens）在本 worktree 有环境性误报：其等价于在仓库根无 venv 上下文跑 pyright，
     会误报导入解析；项目钉住配置下全部干净。可考虑根级 `pyrightconfig.json` 指向 `backend/.venv`
     （仓库根配置超出本票 Ownership，未动）

## 协调者复核(2026-10-08, wave-1 集成)

- 评审:reviewer fresh-context 裁决 **OK with notes**(run 5fdfc907)。
- 协调者独立复门:worktree 内 pytest **394 passed** + 前端三件套绿;合并后主区 425 passed 全量吻合。
- 行为冒烟:零表单 `POST /api/v1/sessions` 空 body → title「未命名备课」/ title_edited false / granularity「标准」,删除 200(冒烟会话已清理)。
- worker 移交的 docs/acceptance-manual.md:78 旧弹窗流程已由协调者收口(重写为零表单直开+自动命名观察点,commit 见 docs(acceptance))。
- P2 留档待补:①截断边界测试强度(FIRST_TURN 恰 30 字,断言在不截断时同样通过);②迁移 prep_sessions 分支(title_edited 补列+回填)无 legacy 库用例。
- **Status: done(独立复验通过;P2 测试加固可后续小票)**
