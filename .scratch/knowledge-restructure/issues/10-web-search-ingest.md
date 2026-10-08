# 10: 联网检索并入库（手动扳机）

**What to build:** 知识库未命中时，教师可以点「联网检索并入库」：系统用博查搜索，把结果按
**文献笔记**入库（来源=网页），提取知识点走冲突审核；之后这批知识与库内知识同管道参与备课。
**不自动联网**，生成时不直接把网页内容拼进课件（教师已确认口径）。

**Blocked by:** 06（复用文献笔记与入库管道——网页结果就是一份来源=网页的文献笔记）

**Status:** ready-for-agent

- [x] 能力接线：走既有搜索能力工厂（博查已配 Key）；未配置时 503 + 去设置页引导
  （`provider_not_configured` 全局口径，不返回假结果）
- [x] 会话界面：空命中提示旁提供「联网检索并入库」按钮（仅教师手动触发）；
  触发后给出进行中反馈与结果去向说明（入知识库，不入本次课件）
- [x] 入库管道：搜索结果 → 文献笔记（来源=网页，含标题/URL/摘要）→ 分块 → 提取知识点 →
  冲突检测 → 待审队列；与上传资料同一条管道，不另写第二套逻辑
- [x] 文案：按钮与状态用「联网检索并入库」（CONTEXT.md §4 词条）；不承诺「自动联网」
- [x] 离线测试：搜索替身覆盖 成功入库/零结果/未配置 503 三态；冲突联动走既有替身
- [x] `uv run pytest -q`、前端三件套全绿
- [ ] 教师配合真实 Key 冒烟：真实检索一次并入库、进冲突队列（【收尾】教师执行，不阻塞交付）

【Ownership】
- 可改：搜索能力接口（如需补方法）、会话/编排层（按钮端点）、API 层（新端点 + OpenAPI 注解）、
  备课会话区前端、测试
- 禁区：`app/core/asr/paraformer.py` 与音频测试（DashScope 史实名）；自动联网（spec.md 范围外）；
  生成器直接消费网页原文（必须入库后走检索）

【约束】网页知识点同样受冲突审核约束（待审不入图谱，ADR-0006）；不绕过「未配置 → 503 引导」。


## 交付记录

- 实现位置：`/tmp/edumind-w10`，分支 `lane-w10-web-ingest`，基线 `caef665`；仅实现本票，Status 未改。独立复核由协调者后续派发，本记录不是复核通过结论。
- 新端点：`POST /api/v1/knowledge/web-search/ingest`，请求为 `query`（去空白后 1–500 字符）、`k`（1–5，默认 5）；响应 `query / ingested / documents`。`ingested` 是已接收数，不是处理成功数，资料初始为「处理中」，知识库原有列表／详情轮询跟进到终态。零结果为 200＋0＋空列表，搜索未配置（含显式博查无 Key）为 503＋`provider_not_configured`＋设置引导，无新增资料。
- 知识引擎 `web_ingest.py` 负责检索与建资料；薄路由只转发与交后台任务。`pipeline.parse_document` 新增可选文本入口与来源参数，网页仅跳过文件解析器，分块／向量化／知识提取／冲突检测／文献笔记／失败状态仍使用上传资料的同一段代码。没有本地原件的网页资料 `file_path` 留空；完整标题、URL、摘要保存在入库正文与分块，资料名为标题，文献笔记来源为「网页」。修正 `build_note` 原有来源参数未传入 upsert 的缺口，未配置对话模型时也保留网页来源且不编造概要。
- 会话生成回复在「知识库为空」和「知识库未命中相关内容」两种提示旁提供手动按钮，主题取该条回复的 `intent.topic`；不点击不检索。进行中、零结果、已接收待后台处理、失败和 503 设置链接均有反馈，明确入知识库、不改变本次课件。没有主题的旧记录禁用按钮并解释。已接收后本次按钮禁用以减少重复点击；重开页面可再次手动检索，不新增去重策略。
- 离线测试：新增 `test_web_search_ingest.py` 共 9 项，覆盖成功／零结果／auto 未配置／显式博查无 Key／真实共享管道冲突待审隔离／未配置对话模型来源／输入校验／后台失败可观察／会话与生成物无副作用。能力替身仅扩展 `tests/support/fakes.py`，无生产假响应。
- 红绿证据：先跑新增测试 7 项全部因端点 404 失败；实现后针对本票及文献笔记、既有搜索的 12 项回归通过。最终本票 9 项通过，全量 `cd backend && uv run pytest -q`：436 passed，退出 0；`uv run ruff check .`：All checks passed，退出 0。
- Ruff 基线说明：初次全量因两个既有清理脚本 EXE001 失败，Git 跟踪 100644，而主仓库 FUSE 实际权限掩盖了这一点。经 supervisor 明确批准，仅在本 worktree 对 `cleanup_demo_data.py`、`cleanup_orphan_outputs.py` 本地 chmod＋x 后全绿；脚本内容、Git 模式均不 stage／commit，不加 noqa／ignore。协调者将单独修复仓库可执行位并复验集成 HEAD。
- 前端：`npm run gen:api` 生成快照与类型（37 路径、42 操作），`npm run lint`、`npm run build`（含 tsc）、`npm run check:routes` 全退出 0。额外离线 SSR／narrowing 核验：空库与无相关命中均显示入口、命中不显示、缺失主题安全收窄。自审实际 diff 与 `git diff --check` 通过。
- 扁平风格自检：新增容器直角黑框、黑白与强调色、Button 复用默认／悬停反色／聚焦／禁用四态；状态文案有 status／alert 语义，无新圆角、阴影、灰底、渐变、位移或循环动效。机器扫描 109 文件、10 条规则零违规。未新增弹层、图谱或外链字体。
- 未执行：浏览器真实交互与真实博查 Key 冒烟（检索入库并产生真实待审冲突），仍待教师配合，不勾选人工项。保留既有后台任务重启中断语义、无去重、知识提取尽力而为语义。npm install 报既有依赖审计 6 项（2 low、4 high），未扩大范围升级；构建仍有既有大块体积提示。


### 评审处置（pass 1）

- 已读取独立两轴报告：`w10-spec.md` 无问题；`w10-standards.md` 的 P2「网页失败仍指向重新上传」经协调者确认有效，本次仅做来源恢复指引适配。Status 不改；本次修复仍待协调者复门与针对性独立复核。
- 后端：`failure_reason_for` 增加默认保持上传资料口径的 `source` 参数。网页通用失败与服务重启中断均引导回备课会话、手动再次点击「联网检索并入库」；`ProviderNotConfigured` 优先保留原设置引导。不改变共享解析流程、任务生命周期、冲突隔离或状态集合。
- 前端共享文件精确变更（供与 07 合并）：`DocumentDetail.tsx` 在详情主组件以 `file_type／literature_note.source` 判断网页来源，向 `DetailHeader／StatusBlock／LiteratureNoteSection` 传 `isWeb`；仅网页失败覆盖状态长说明、将恢复按钮替换为指向 `/lesson-prep` 的 Link，网页未配置能力显示去设置引导，网页文献笔记未配置不再要求上传原件。普通上传资料的重新上传按钮、默认文案、参考资料逻辑均不改；未触碰删除逻辑。
- 检查发现标题行状态标签 tooltip 也沿用上传说法，经 `contact_supervisor` 额外明确批准：`DocumentStatus.tsx` 仅增加可选 `hint` 覆盖，默认仍用原 `STATUS_HINT[status]`；只由详情网页失败场景传正确提示，不改列表默认值或解析状态类型。
- 先红证据：后端强化网页失败文案并新增未配置／中断回归后，`uv run pytest -q tests/test_web_search_ingest.py tests/test_documents.py` 为 3 failed、14 passed；3 项分别暴露错误上传指引、缺少来源参数与中断指引未适配。真实详情 SSR 回归 `node scripts/check-document-detail-recovery.mjs` 初次退出 1，网页正文仍显示重新上传。
- 转绿证据：修复后针对 `test_web_search_ingest.py／test_documents.py／test_generation_failures.py` 共 23 passed；新增 SSR 脚本不添加组件导出或测试接口，通过真实详情＋QueryClient 快照覆盖网页 file_type／source 分支、正文与 tooltip、恢复目标、未配置去设置、普通上传兼容。脚本退出 0。类型检查 `npx tsc -b` 退出 0；本次不变更 OpenAPI，未重生成或手抄接口类型。
- 最终五门全部真实运行：后端 `uv run pytest -q`＝438 passed、退出 0；`uv run ruff check .`＝All checks passed、退出 0；前端 `npm run lint`、`npm run build`、`npm run check:routes` 均退出 0。额外来源恢复 SSR 脚本退出 0，`git diff --check` 通过；日志保存在本 worktree `.scratch/w10-pass1-gates/`（不提交日志）。两个既有清理脚本仅获准本地＋x供 Ruff，内容与仓库模式不暂存、不提交。
- 扁平风格自检：恢复链接复用 Button 的黑白反色／聚焦／禁用四态、直角黑框，设置引导复用既有扁平 Notice，无新样式或状态；109 文件、10 条禁用 class 规则零违规。人工浏览器点击、真实 Key 联网入库与真实待审冲突冒烟仍未执行；保留待办，不勾选人工项。
