# 02: TCP 演示数据清理（一次性）

**What to build:** 教师的知识库回到干净起点：TCP 演示资料与其衍生的全部数据（知识点、关系、
待审冲突、向量、文件）不再出现在任何区。教师已明确批准全删（2026-10-08）。

**Blocked by:** None (can start immediately)

**Status:** done

影响面（已核实，`backend/edumind.db` + `backend/data/vectors.db`）：
- `documents` 3 行：`7679299b…`（讲义教师版）、`a181d7d2…`（板书照片）、`9eb4e0bc…`（2024 修订版）
- `knowledge_nodes` 13 行（全部节点都是 TCP）；`knowledge_edges` 10 行（全部在这 13 点之间）
- `conflicts` 1 行（doc_id=9eb4e0bc…，定义冲突）
- `vectors.db`：`chunks`/`chunk_embeddings` 中 doc_id 属于上述 3 份的行；`node_titles`/
  `node_title_embeddings` 中 13 个节点的行
- `data/uploads/` 5 个文件：3 个属于上述资料 + 2 个上传被拒遗留的孤儿 wav
  （`84832801…wav`、`e148cc88…wav`，不在 documents 表）
- `questions` 5 行**不受影响**（`question_knowledge` 为空，无关联）

- [x] 一次性脚本（`backend/scripts/` 下）支持 `--dry-run`：输出将删的每一行/每一文件清单
  （实现为「默认即 dry-run，真删须显式 `--execute`」；`--dry-run` 旗标也接受，行为同默认，更防误删）
- [x] 真删前备份：`cp edumind.db edumind.db.bak-<日期>` + 记录 vectors.db 状态
  （实现偏差：用 SQLite backup API（WAL 下对在线服务安全）把两个库都备份到
  `backend/data/cleanup-backup-20261008-112740/`（edumind.db 417792 B + vectors.db 8491008 B，
  均被 .gitignore 的 `*.db` 覆盖不入库）；比票面字面多备了 vectors.db 整库）
- [x] 执行前核对：无任何 `prep_sessions.reference_doc_ids` 指向这 3 份资料（有则先报告再处理）
  （门禁实现为脚本内置：发现引用即拒绝执行；真删前现场核验 3 个会话引用全空，通过）
- [x] 删后验证：知识库区列表为空、知识图谱区为空、冲突审核队列为空、题库 5 题完好；
  `uv run pytest -q` 全绿（测试用的是隔离库，不应受影响——若受影响说明测试漏了密封，另修）
  （GET /documents `[]`、GET /knowledge/graph `{nodes:[],edges:[]}`、GET /conflicts `[]`、
  GET /questions 5 题、`uv run pytest -q` → 400 passed）
- [x] 验证文件数：`data/uploads/` 目录清空（删后 `ls -A | wc -l` = 0）

【Ownership】
- 可改：`backend/scripts/`（新脚本）、`backend/data/`（数据本体）、`backend/edumind.db`
- 禁区：`app/` 产品代码（本票不改行为）；`data/output/`（那是 03 票的范围）

【约束】不可逆操作：dry-run 清单先给维护者过目再真删（维护者已在对话中批准全删，
脚本仍须先 dry-run 留痕）。

## 交付记录（2026-10-08，wave-1 Lane D23）

- 分支/提交：`main`，票 02 代码与票文件同一提交（脚本+测试+本票）。
- dry-run 对账（真删前现场重核，与票面逐项相符）：documents 3、knowledge_nodes 13、
  knowledge_edges 10、conflicts 1、vectors chunks 6（1+4+1）、node_titles 13、
  uploads 5 文件（3 属资料 + 2 孤儿 wav）；`prep_sessions.reference_doc_ids` 3 会话全空。
- 真删：`--execute` 一次通过；删后自证（脚本内置）六面全零、questions 5 题未动；
  备份：`backend/data/cleanup-backup-20261008-112740/`（edumind.db + vectors.db，SQLite backup API）。
- 幂等/防呆验证：复跑 `--execute` 被 `CleanupRefused`（现场全零）拒绝；复跑 dry-run 报「已清理过」。
- 命令与结果：`uv run pytest tests/test_demo_cleanup_script.py -q` → 8 passed；
  `uv run pytest -q` → 400 passed；`uv run ruff check scripts/cleanup_demo_data.py
  tests/test_demo_cleanup_script.py` → 全过（仓库级 `ruff check .` 在本机有 145 个既有
  EXE002 噪音：/mnt/Data fuse 挂载强制可执行位所致，非本票引入）。
- 新建文件：`backend/scripts/cleanup_demo_data.py`、`backend/tests/test_demo_cleanup_script.py`。
- 遗留：①`backend/data/edumind.db` 有个 0 字节杂散文件（非本票范围，未动）；
  ②题库 5 题内容是 TCP 题（「自编」），票面明确保留，未动；
  ③删除脚本为一次性，保留在 scripts/ 供复核与复用其门禁模式，如需可后续移除。

## 协调者复核(2026-10-08, wave-1 集成)

- 评审:reviewer fresh-context 裁决 **OK with notes**(run 498fe34c)。
- 协调者独立核验(只读):edumind.db 计数 documents/nodes/edges/conflicts = 0/0/0/0,questions = 5 分毫未动;vectors.db 四表(chunks/chunk_embeddings/node_titles/node_title_embeddings)全 0;uploads 目录空;备份目录两 db 为有效 SQLite 且非零;两 commit(git show --stat)仅含 scripts/tests/票文件。
- P2 记录在案:①uploads 5 文件删前无文件级副本(spec 的「目录备份」未覆盖到,数据为教师批准全删的演示/垃圾件);②脚本 dry-run 用 sqlite3.connect 打开主库,文件缺失会静默建空库,复用该模式时应改 mode=ro。
- **Status: done(独立复验通过)**
