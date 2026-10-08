# 01: 检索相关度阈值与诚实空命中

**What to build:** 教师任问一个主题，生成只融合**相关**的知识库内容；知识库里没有相关内容时，
回复明确说「知识库未命中相关内容，由 AI 直接生成」，绝不再把不相关的知识点塞进课件
（杀掉「讲秦始皇出 TCP」的污染根子）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `app/knowledge/retrieval/search.py` 的 `search_hits` 按**余弦距离阈值**过滤命中：
  超阈值的命中一律丢弃（不是降权）；阈值可配置（先例：`app/db/engine.py` 的
  `conflict_distance_threshold`），默认值保守取宽，避免误杀
- [ ] 空命中分两种口径落到前端：**库为空**（现状文案保留）与**库非空但未命中相关内容**（新文案
  「知识库未命中相关内容，由 AI 直接生成」）；`GeneratedResult` 的提示按后端语义显示，
  不再在「命中了不相关内容」时谎报「已融合本地知识库」
- [ ] 离线测试：替身向量下覆盖 命中/超阈值丢弃/空库/未命中 四态；污染场景回归测试
  （query=秦始皇 + 库内只有 TCP 向量 → 命中为空）
- [ ] `uv run pytest -q` 全绿；`uv run ruff check .` 干净
- [ ] 教师配合的真实向量化冒烟：上传一份非 TCP 资料，问无关主题，课件不含 TCP（【收尾】教师执行）

【Ownership】
- 可改：`app/knowledge/retrieval/`、`app/knowledge/vector_store.py`、`app/db/engine.py`（新增配置）、
  `app/core/orchestrator.py`（命中语义）、前端 `lesson-prep/GeneratedResult.tsx` 及其 narrowing、
  `backend/tests/`、OpenAPI 注解
- 禁区：`app/knowledge/conflict.py` 的阈值语义（那是冲突检测的，别共用水位）；四种关系模型；
  `frontend/src/api/generated/`（gen:api 生成物）

【约束】面向教师的文案用 CONTEXT.md 词汇；注解缺失=文档缺失（OpenAPI 是唯一事实源）。
