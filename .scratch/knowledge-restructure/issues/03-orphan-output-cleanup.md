# 03: data/output 历史孤儿文件清理（一次性）

**What to build:** `backend/data/output/` 里不被任何生成物版本或会话消息引用的历史文件
（Windows 演示时代遗留，约 3366 个条目）清空；现役生成物的下载不受影响。教师已明确批准
（2026-10-08，默认「不动」的方案被推翻）。

**Blocked by:** None (can start immediately)

**Status:** done

判定口径（先核实再执行）：
- **保留**：文件名出现在 `artifact_versions.filename`，或被 `session_messages.artifacts`
  （JSON 文本列）引用的文件
- **删除**：其余全部

- [x] 一次性脚本支持 `--dry-run`：输出保留清单（预期 ≥6 个，与 `artifact_versions` 6 行对账）
  与删除清单（预期 ~3366 个）；两个数字对不上时**停在报告**，人工核对差异
  （现场对账：artifact_versions 已增至 9 行——票面写作时 6 行，之后又生成过两轮；保留 9 ≥ 6，
  且 9 行逐一在盘上保留；删除恰 3366 = output 3375 − 9，与票面预期精确相符；
  实现为「默认即 dry-run，真删须显式 --execute」，另有同名旗标接受显式声明）
- [x] 真删前备份：删除清单打包为一个 tar（放 `data/` 外，如 `/tmp/` 或仓库外目录），再删
  （`/tmp/edumind-output-orphans-20261008-123427.tar`，113 MB / 3366 个成员，
  打包后校验成员数与删除清单一致才开删）
- [x] 删后验证：生成物区 6 个版本逐个「下载/在新标签页打开」全部成功；
  「你好你是谁」与「讲一次函数」两会话的课件/教案/提纲预览正常
  （现库 9 个版本逐个走 `GET /artifacts/{id}/download` 与 `GET /artifacts/{id}` 全部 200
  且字节数正常；三个会话（讲一次函数×2 + 你好你是谁）的 `GET /sessions/{id}/artifacts` 全 200）
- [x] `uv run pytest -q` 全绿（不改产品代码，应天然全绿；红则说明测试依赖了数据目录，另修）
  （409 passed，含两个清理脚本自身的 17 个新测试）

【Ownership】
- 可改：`backend/scripts/`（新脚本）、`backend/data/output/`
- 禁区：`app/` 产品代码；`data/uploads/` 与两个 .db（02 票范围）

【约束】不可逆操作：dry-run 报告先行，tar 备份兜底；对账不过不平删。

## 交付记录（2026-10-08，wave-1 Lane D23）

- 分支/提交：`main`，票 03 代码与票文件同一提交（脚本+测试+本票；另含 pi-lens 对票 02
  两个已提交文件的纯排版重排，测试全绿佐证语义未变）。
- dry-run 对账（真删前现场重核）：output 3375 个文件（2395 docx + 920 pptx + 60 html，无子目录）；
  保留 9 = artifact_versions 9 行逐一在盘保留，消息 artifacts 额外引用 0（三份生成回复引用的
  正是这 9 个版本文件名）；删除 3366 与票面预期精确相符；无坏 JSON、无缺失、无非文件条目。
- 真删：`--execute` 一次通过；tar 备份 3366 成员校验一致后开删；删后自证（脚本内置）
  剩 9 个保留文件、孤儿全清。
- 验证：9/9 版本 download+detail 全 200；三会话生成物列表全 200；`uv run pytest -q` → 409 passed。
- 幂等/防呆验证：复跑 execute 因「无孤儿可删」走 no-op 分支（数量对账仅在删除集非空时生效，
  盘面漂移仍被其余门禁拦截）；坏 JSON、版本文件缺失、保留数不足、删除数不符均单测覆盖为拒绝。
- 新建文件：`backend/scripts/cleanup_orphan_outputs.py`、
  `backend/tests/test_orphan_output_cleanup_script.py`。
- 遗留：①tar 备份在 /tmp（票面指定位置），重启即清，如需长期留存请人工迁移；
  ②一次性脚本保留在 scripts/ 供复核，如需可后续移除。

## 协调者复核(2026-10-08, wave-1 集成)

- 评审:reviewer fresh-context 裁决 **OK with notes**(run 498fe34c)。
- 协调者独立核验(只读):`data/output/` 恰 9 文件,与 artifact_versions.filename 对账两差集均为空;删后下载/预览验证记录在交付记录。
- **P1 补记(须教师知会)**:唯一删除清单备份 `/tmp/edumind-output-orphans-20261008-123427.tar` 已被系统清理(2026-10-08 午后 /tmp 回收),3366 个已删文件现无留痕副本。删除本身经教师批准且不可逆,终态正确;此补记为留痕完备性声明,无法挽回。
- P2 记录在案:tar 默认落 /tmp 易失位置,复用该模式时应默认耐久路径。
- **Status: done(独立复验通过;含上述知会事项)**
