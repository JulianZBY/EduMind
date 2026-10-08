# 01: 检索相关度阈值与诚实空命中

**What to build:** 教师任问一个主题，生成只融合**相关**的知识库内容；知识库里没有相关内容时，
回复明确说「知识库未命中相关内容，由 AI 直接生成」，绝不再把不相关的知识点塞进课件
（杀掉「讲秦始皇出 TCP」的污染根子）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] `app/knowledge/retrieval/search.py` 的 `search_hits` 按**余弦距离阈值**过滤命中：
  超阈值的命中一律丢弃（不是降权）；阈值可配置（先例：`conflict_distance_threshold`，
  实际住在 `app/config.py` 的 Settings），默认值保守取宽，避免误杀（默认 0.8）
- [x] 空命中分两种口径落到前端：**库为空**（现状文案保留）与**库非空但未命中相关内容**（新文案
  「知识库未命中相关内容，由 AI 直接生成」）；`GeneratedResult` 的提示按后端语义显示，
  不再在「命中了不相关内容」时谎报「已融合本地知识库」
- [x] 离线测试：替身向量下覆盖 命中/超阈值丢弃/空库/未命中 四态；污染场景回归测试
  （query=秦始皇 + 库内只有 TCP 向量 → 命中为空）
- [x] `uv run pytest -q` 全绿；`uv run ruff check .` 新增违规为零（存量 EXE002 为 fuse
  挂载把全部文件标为可执行的仓库级既有噪音，见交付记录）
- [ ] 教师配合的真实向量化冒烟：上传一份非 TCP 资料，问无关主题，课件不含 TCP（【收尾】教师执行）

【Ownership】
- 可改：`app/knowledge/retrieval/`、`app/knowledge/vector_store.py`、`app/db/engine.py`（新增配置）、
  `app/core/orchestrator.py`（命中语义）、前端 `lesson-prep/GeneratedResult.tsx` 及其 narrowing、
  `backend/tests/`、OpenAPI 注解
- 禁区：`app/knowledge/conflict.py` 的阈值语义（那是冲突检测的，别共用水位）；四种关系模型；
  `frontend/src/api/generated/`（gen:api 生成物）

【约束】面向教师的文案用 CONTEXT.md 词汇；注解缺失=文档缺失（OpenAPI 是唯一事实源）。

## 交付记录（2026-10-08，票 01 实施完成）

**分支**：`pi-subagents/t01-ae80bd0-6998-s0-t0`（基于 main@HEAD = c726607 的 worktree）

**代码提交**：`794be6d`（feat(knowledge): 检索相关度阈值与诚实空命中；12 文件，+413/−20）

**实现要点**：
- 阈值语义：`search_hits` 对每条命中现算**余弦距离**（`_cosine_distance`，1 − 余弦相似度）
  并按 `retrieval_distance_threshold`（新增于 `app/config.py`，默认 0.8，保守取宽）过滤，
  超阈值一律丢弃、保留原排名。注意：向量库 `chunk_embeddings` 表是 sqlite-vec 默认 L2 度量，
  存量 distance 受向量模长影响不能直接比余弦阈值，故从 store 取原始向量（`search(with_embeddings=True)`，
  float32 小端字节串）现算；存量库无需迁移，冲突检测的标题索引（cosine 度量）未动。
- 空命中两口径：`RetrievalResult` 增 `library_empty`（两档检索策略在命中为空时探测
  `VectorStore.chunk_count()` 新方法）；orchestrator artifacts 新增 `knowledge_empty`；
  回复文案三口径（已融合 / 知识库为空 / 知识库未命中相关内容，由 AI 直接生成）；
  前端 `narrowing.readKnowledgeOutcome` 三态读法（历史记录无 `knowledge_empty` 字段时
  沿用当时的「知识库为空」文案），`GeneratedResult` 按后端语义显示。
- OpenAPI 注解：`/api/v1/chat` 生成回复示例修正 `knowledge_hits: 3` → `true`，
  并补 `knowledge_empty: false`。

**命令与结果**：
- `uv run pytest -q` → **403 passed**（含新增 11 条：`tests/test_retrieval_threshold.py`）
- `uv run ruff check . --statistics` → 改动前（HEAD 基线，`git stash -u` 对比）145 条 EXE002，
  改动后 146 条 EXE002：增量恰为本票新建的 1 个测试文件撞上同一现象，**零新增规则违规**。
  EXE002 全集是 `/mnt/Data` fuse 挂载把所有文件报成 777（git index 实为 100644，
  `core.fileMode=false`，`chmod` 实测 no-op）的仓库级既有噪音，按协调者指令不改 ruff 配置、
  不 chmod；diff 的 10 个后端文件收窄检查 = 10 条 EXE002、其余规则零违规。
- `npm run lint` → 禁用 class 扫描 109 文件零违规 + oxlint 通过；
  `npm run build` → tsc -b + vite 构建成功（chunk >500kB 警告为既有）；
  `npm run check:routes` → 七条路由全部可达，默认路由 = 备课会话。

**新建 / 改动文件**：
- 新建：`backend/tests/test_retrieval_threshold.py`（四态 + 阈值可配 + 不共用冲突水位 +
  污染回归 + 回复文案三口径 + /chat 全链路空库/未命中/命中上下文断言）
- 后端：`app/config.py`、`app/knowledge/retrieval/{base,search,vector,vector_graph}.py`、
  `app/knowledge/vector_store.py`、`app/core/orchestrator.py`、`app/core/conversation.py`、
  `app/api/v1/chat.py`
- 前端：`src/areas/lesson-prep/{narrowing.ts,GeneratedResult.tsx}`
- 禁区零触碰：`app/knowledge/conflict.py`（阈值语义）、四种关系模型、
  `frontend/src/api/generated/`（gen:api 生成物）均未改动（git diff 核对）。

**遗留问题**：
1. 【收尾·教师执行，不阻塞】真实向量化冒烟：上传一份非 TCP 资料，问无关主题，课件不含 TCP。
2. EXE002（146 条）为仓库级既有噪音；后续如需「ruff check . 干净」可在挂载层解决
   （或为 EXE 规则做仓库级豁免），属仓库工程决策，不在本票 Ownership 内。
3. `app/core/orchestrator.py` L62/L67 与 `app/core/llm/provider_instances.py` 存在既有的
   类型收窄/静态模式提示（触碰文件即全文件复扫所现，git diff 证实非本票引入），未顺手修，
   避免扩票。
