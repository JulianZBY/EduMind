# 03: data/output 历史孤儿文件清理（一次性）

**What to build:** `backend/data/output/` 里不被任何生成物版本或会话消息引用的历史文件
（Windows 演示时代遗留，约 3366 个条目）清空；现役生成物的下载不受影响。教师已明确批准
（2026-10-08，默认「不动」的方案被推翻）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

判定口径（先核实再执行）：
- **保留**：文件名出现在 `artifact_versions.filename`，或被 `session_messages.artifacts`
  （JSON 文本列）引用的文件
- **删除**：其余全部

- [ ] 一次性脚本支持 `--dry-run`：输出保留清单（预期 ≥6 个，与 `artifact_versions` 6 行对账）
  与删除清单（预期 ~3366 个）；两个数字对不上时**停在报告**，人工核对差异
- [ ] 真删前备份：删除清单打包为一个 tar（放 `data/` 外，如 `/tmp/` 或仓库外目录），再删
- [ ] 删后验证：生成物区 6 个版本逐个「下载/在新标签页打开」全部成功；
  「你好你是谁」与「讲一次函数」两会话的课件/教案/提纲预览正常
- [ ] `uv run pytest -q` 全绿（不改产品代码，应天然全绿；红则说明测试依赖了数据目录，另修）

【Ownership】
- 可改：`backend/scripts/`（新脚本）、`backend/data/output/`
- 禁区：`app/` 产品代码；`data/uploads/` 与两个 .db（02 票范围）

【约束】不可逆操作：dry-run 报告先行，tar 备份兜底；对账不过不平删。
