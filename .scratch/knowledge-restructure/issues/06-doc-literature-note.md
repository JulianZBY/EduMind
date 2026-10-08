# 06: 文献笔记（模型 + 入库管道 + 资料详情）

**What to build:** 教师上传教学资料后，知识库区的资料详情里能看到它的**文献笔记**：资料概要
+ 由这份资料提取出的知识点索引（ADR-0007）。资料的管理入口从此落在文献笔记上。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] 数据模型：文献笔记（资料概要、来源=教学资料或网页、与教学资料 1:1），
  新表进数据模型并带中文语义注释
- [x] 入库管道：解析完成后自动生成文献笔记；知识提取完成时把该资料的知识点索引写进去
- [x] 对话模型未配置时：分块与解析照常入库，文献笔记不生成、详情里显示「未配置」引导
  （不返回假摘要，AGENTS.md 铁律）
- [x] 知识库区资料详情呈现文献笔记：概要 + 知识点索引列表，索引可点到知识点
- [x] 离线测试：有对话模型替身时生成完整、未配置时引导正确
- [x] `uv run pytest -q`、`npm run lint`、`npm run build`、`npm run check:routes` 全绿

【Ownership】
- 可改：数据模型与迁移、入库管道、documents API、知识库区前端、测试
- 禁区：删除联动（07 票范围，本票不做删除）；`app/core/asr/paraformer.py`（DashScope 史实）

【约束】「文献笔记」是 CONTEXT.md §4 正式术语，界面照用；不做删除入口（07 票）。

## 交付记录（2026-10-08，票 06 implement）

- **分支**：`pi-subagents/t06-eb5c1ed-919c-s0-t0`；**commit**：`4960eb7`（feat(knowledge): 文献笔记——模型、入库管道与资料详情呈现）
- **命令与结果**：
  - `cd backend && uv sync --frozen` ✓；`cd frontend && npm install` ✓（冷 worktree 首次装依赖）
  - `uv run pytest -q` → **395 passed**（含新增 3 条文献笔记契约测试）；`cd frontend && npm run lint` → ✓（check:classes 109 文件 0 违规 + oxlint）；`npm run build` → ✓（tsc -b + vite）；`npm run check:routes` → ✓ 七路由可达
  - `uv run ruff check .` → 代码级零发现；本机报 147 条 EXE002 全部为 fuse 挂载强制 777 的存量伪象（142 个未触碰文件同样中招；`--ignore EXE002` → All checks passed；git 提交实录 mode 100644）
  - 仓库自配 pyright（钉 `.venv`）对全部触碰文件 0 errors
- **新建**：`backend/app/knowledge/literature_note.py`（文献笔记管道：概要生成 + 1:1 落库 + 知识点索引）、`backend/tests/test_literature_note.py`
- **改动**：`backend/app/db/models.py`（新表 literature_notes）、`backend/app/knowledge/pipeline.py`（解析完成后调 build_note）、`backend/app/api/v1/documents.py`（详情返回 literature_note + OpenAPI 注解）、`backend/tests/support/fakes.py`（FakeLLM 概要口径、FakeTranscriber 可传 transcript）、`frontend/src/areas/knowledge/DocumentDetail.tsx`（文献笔记区：概要 + 可点索引；未配置给引导）、`frontend/openapi/openapi.json` 与 `frontend/src/api/generated/*`（gen:api 产物）
- **禁区核对**：零删除入口（07 票范围）；`app/core/asr/paraformer.py` 未触碰
- **遗留**：
  - 索引是入库时点快照：冲突裁决「接受新」替换节点后，索引条目不自动改写（关联治理归 07/10 票口径）
  - 老存量资料（本票之前入库的）无文献笔记，详情如实报「未生成」，不做补生成
  - 环境备注：本机 /mnt/Data fuse 挂载对所有文件强制 777，ruff EXE002 与编辑器 lint 的「executable/shebang」「依赖解析」报错均属该伪象；冷 worktree 需先 `uv sync --frozen` 让钉定工具链生效
