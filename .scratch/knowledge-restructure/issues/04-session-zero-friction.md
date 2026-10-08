# 04: 新建备课会话零表单直开

**What to build:** 教师点「新建备课会话」**立即**进入一个新会话开始说话：不弹窗、不勾资料、
不选粒度。会话先叫「未命名备课」，教师发出首条消息后自动以消息内容命名；教师手动改过名，
之后不再自动改。改名入口常驻。参考资料改为备课过程中随时挂/换（会话内已有该能力，保留）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `NewSessionDialog` 与 `ReferencePicker` 从新建流程退场：点「新建备课会话」→
  `POST /api/v1/sessions` → 导航到 `/lesson-prep/{id}`，全程无弹层
  （`?new=1` 的 URL 状态机制一并清理或改造，不留死链）
- [ ] 后端支持「未命名备课」初始态与自动命名：首条教师消息后自动以消息内容命名；
  教师手动改名后自动命名停用（需要最小 schema 标记，如 `title_edited`；落库带中文语义注释）
- [ ] 改名入口：会话头/侧栏可inline改名（走既有 `PATCH /sessions/{id}`）
- [ ] 追问粒度默认「标准」，会话内 `GranularityPicker` 照旧可改（弹窗里的粒度选择随弹窗消失）
- [ ] 词汇表口径：「未命名备课」「备课会话」照 CONTEXT.md §2 用词
- [ ] 离线测试：创建即开、首条消息自动命名、手动改名后不再自动覆盖 三态
- [ ] `uv run pytest -q`、`npm run lint`、`npm run build`、`npm run check:routes` 全绿

【Ownership】
- 可改：`frontend/src/areas/lesson-prep/`（`NewSessionDialog.tsx`、`SessionSidebar.tsx`、
  `ConversationAxis.tsx`、queries）、`backend/app/api/v1/sessions.py`、`app/core/session_service.py`、
  `app/db/`（sessions 表）、`backend/tests/`
- 禁区：生成物区与生成流程；`ReferencePicker` 若被会话内挂资料复用则保留组件本体、只退新建流程

【约束】前端视觉过 `docs/style/minimalist-flat.md` 自检清单（零阴影/零渐变/border-2 border-black/
rounded-none/hover 反色）；文案中文全角标点。
