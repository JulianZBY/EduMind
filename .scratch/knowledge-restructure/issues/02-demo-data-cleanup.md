# 02: TCP 演示数据清理（一次性）

**What to build:** 教师的知识库回到干净起点：TCP 演示资料与其衍生的全部数据（知识点、关系、
待审冲突、向量、文件）不再出现在任何区。教师已明确批准全删（2026-10-08）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

影响面（已核实，`backend/edumind.db` + `backend/data/vectors.db`）：
- `documents` 3 行：`7679299b…`（讲义教师版）、`a181d7d2…`（板书照片）、`9eb4e0bc…`（2024 修订版）
- `knowledge_nodes` 13 行（全部节点都是 TCP）；`knowledge_edges` 10 行（全部在这 13 点之间）
- `conflicts` 1 行（doc_id=9eb4e0bc…，定义冲突）
- `vectors.db`：`chunks`/`chunk_embeddings` 中 doc_id 属于上述 3 份的行；`node_titles`/
  `node_title_embeddings` 中 13 个节点的行
- `data/uploads/` 5 个文件：3 个属于上述资料 + 2 个上传被拒遗留的孤儿 wav
  （`84832801…wav`、`e148cc88…wav`，不在 documents 表）
- `questions` 5 行**不受影响**（`question_knowledge` 为空，无关联）

- [ ] 一次性脚本（`backend/scripts/` 下）支持 `--dry-run`：输出将删的每一行/每一文件清单
- [ ] 真删前备份：`cp edumind.db edumind.db.bak-<日期>` + 记录 vectors.db 状态
- [ ] 执行前核对：无任何 `prep_sessions.reference_doc_ids` 指向这 3 份资料（有则先报告再处理）
- [ ] 删后验证：知识库区列表为空、知识图谱区为空、冲突审核队列为空、题库 5 题完好；
  `uv run pytest -q` 全绿（测试用的是隔离库，不应受影响——若受影响说明测试漏了密封，另修）
- [ ] 验证文件数：`data/uploads/` 目录清空

【Ownership】
- 可改：`backend/scripts/`（新脚本）、`backend/data/`（数据本体）、`backend/edumind.db`
- 禁区：`app/` 产品代码（本票不改行为）；`data/output/`（那是 03 票的范围）

【约束】不可逆操作：dry-run 清单先给维护者过目再真删（维护者已在对话中批准全删，
脚本仍须先 dry-run 留痕）。
