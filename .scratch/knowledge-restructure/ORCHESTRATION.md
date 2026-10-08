# ORCHESTRATION：knowledge-restructure 多子代理执行计划

> 写给带 `subagent` 工具的会话（本文件由前一会话起草——那个会话的启动时间早于 subagent
> 工具的修复，无法派发）。恢复执行时：读完本文件 + spec.md + 票文件即可开工，无需其他上下文。

## 已就绪

- 票已入库：`.scratch/knowledge-restructure/`（spec + 12 票，HEAD 含
  `50aa52d`/`8df4662`/`8df4662` 后的 lockfile 提交 `ef401e5`）。
- 开发服务在主工作区运行中：后端 127.0.0.1:8000（uvicorn，SQLite WAL）、前端 5174。
  **任何 lane 不得杀/重启它们**。

## Lane board（wave-1，6 条并行 lane）

| Lane | key | 票 | agent | 隔离 | 权威边界 | 验收门 | 交付 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| W01 | t01 | 01 检索阈值+诚实空命中 | worker | `worktree: true` | 票面 Ownership | pytest + ruff | 更新自己的票+交付记录，提交 lane 分支 |
| W04 | t04 | 04 会话零表单+命名 | worker | `worktree: true` | 同上 | 前端三件套 + pytest | 同上 |
| W05 | t05 | 05 时间线折叠 | worker | `worktree: true` | 同上 | 前端三件套 | 同上 |
| W06 | t06 | 06 文献笔记 | worker | `worktree: true` | 同上 | pytest + 前端三件套 | 同上 |
| D23 | t0203 | 02→03 数据清理（串行两张票） | worker | **主工作区**（唯一 writer，wave 期间主区只归它） | 只碰 backend/scripts + data + 自己的票 | dry-run 清单对账→备份→删→验证 | 直接提交 main（脚本票不动产品代码） |
| S11 | t11 | 11 布局 spike | worker | `/tmp/edumind-spike-11`（仓库外，零接触仓库） | 不碰仓库任何文件 | demo 可跑 + 结论 | 结论写 `/tmp/edumind-spike-11/VERDICT.md` 并在回复内联；协调者誊入票 11 交付记录 |

- 推迟：08（等 06 合并，避免 `pipeline.py` 合并冲突）；07←06、09←08、10←06、12←08+11。
- worktree lane 的任务包必须提醒：worktree 无 `.venv`/`node_modules`，先
  `cd backend && uv sync --frozen`、`cd frontend && npm install`（有本地缓存）。
- 任务包必须自洽（cold-start）：内联票文要点 + 指向 worktree 内票文件；implement 技能路径
  `/home/julianzby/.agents/skills/implement/SKILL.md`（内含 tdd/code-review 衔接）；
  仓库纪律源：根 AGENTS.md、backend|frontend AGENTS.md、CONTEXT.md、
  docs/style/minimalist-flat.md（前端票）。

## 发波协议

1. 回复内写一个 ```js workflow 围栏块（`runs.all([...])` 六条，`key` 用上表，
   `label` 动宾式，worktree lane 加 `worktree: true`），同一条回复里调
   `subagent({ workflow: true, async: true })`，然后 **yield 等完成通知**（不要 bg_wait 阻塞）。
2. 每个 writer 完工后：发 fresh-context 只读 `reviewer` 审该 lane diff（P0/P1/P2 + Merge verdict）；
   协调者裁决发现 → 有效阻塞发回原 lane writer 修 → 只重跑受影响的门。
3. 集成：逐 lane merge 回 main（顺序 01→04→05→06，冲突时协调者解决）→ 每次合并后
   `uv run pytest -q` + ruff + 前端三件套 → 更新服务重启验证 → 票内写 `## 协调者复核`
   （独立复验，不采信自报）→ `Status: done`。
4. wave-2：08（知识归类）→ 09（提议审批）；07（删除联动）、10（联网入库）在 06 合并后可并行；
   12（React Flow 画布）等 08+11。lane 板同构。

## 已知坑

- `.scratch/` 在 .gitignore 里，票是 `add -f` 入库的——worktree 里票文件**存在**（已跟踪），
  但新加的未跟踪文件不会出现在别的 worktree。
- D23 执行时 uvicorn 持有 edumind.db：SQLite WAL 并发写安全，别停服务；备份先于删除；
  删除清单必须与票面预期计数对账，对不上就停。
- 12 票的布局选型直接采信 S11 的 VERDICT，不再重新调研。
