# 05: 生成物区版本时间线分组折叠

**What to build:** 教师打开生成物区的版本时间线，看到的是**按生成物分组**的列表：默认只展开
每类生成物的**当前版本**，历史版本与「由哪一版衍生」收起、点开才见。一眼看到的是「现在可用的是
什么」，不是全部历史。不删任何版本（全版本留痕口径不变，CONTEXT.md §3）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] 时间线按 `artifact_type` 分组（课件/教案/提纲/试卷/互动内容），组内默认折叠到当前版本
- [x] 展开组后可见全部版本与版本树关系（parent 衍生连线/标注）；历史版本仍可回看、下载、作基线
  （既有能力不回退）
- [x] 备课会话区右侧面板（`GenerationPreview`）行为不变：仍只显示当前版本 +「共 N 版」入口
- [x] 折叠状态是纯前端交互态，不入库、不进 URL（深链仍直达具体版本）
- [x] `npm run lint`、`npm run build`、`npm run check:routes` 全绿；七条路由可达不回归
- [x] 教师视角核对：折叠时看不到「第 1 版…第 N 版」全部平铺；展开一次后该组保持展开（会话内交互态）

## 交付记录（2026-10-08，lane W05）

**分支**：`pi-subagents/t05-0401f33-d654-s0-t0`（基于 main@c726607）· commit：见该分支 tip。

**现状基线（重要）**：分组折叠的主体在 HEAD 已存在——`SessionVersionCenter` 按后端返回的
`artifact_type` 组逐类渲染 `VersionTimeline`（后端 `app/api/v1/artifacts.py` 已按类别固定次序、
版本号升序返回），每类默认只展示当前版本、历史版本收在折叠开关后。本票在此基础上修掉两处真实差距：

1. **折叠交互态归教师（修 bug）**：原实现 `showHistory = historyOpen || selectedIsHistory` 且开关
   取 `!showHistory`——深链 `?v=` 选中历史版本后，「收起历史版本」点了永远收不回去。
   改为 `historyToggle: boolean | null`：教师没点过开关时跟随深链自动展开（深链仍直达具体版本），
   点过之后以教师表态为准（选中的历史版本由旁边回看列继续呈现）。
2. **折叠开关控件化（对齐票面视觉硬标准）**：开关补折叠箭头（本地 `CollapseChevron`，与
   `components/ui/icons` 同一画法：16×16、strokeWidth 2、currentColor、零阴影零渐变，随按钮
   黑白反色；不进共享图标表以守住本票 Ownership），按钮改 `border-2 border-black` + `rounded-none`
   + `hover:bg-black hover:text-white` 小控件形态，四态齐全（默认/悬停/focus-visible，无禁用态）。

**跑过的命令与结果**（均在 `frontend/`）：

- `npm run lint` → check:classes 109 文件 10 规则零违规 + oxlint exit 0：**过**
- `npm run build` → tsc -b + vite build ✓（chunk 体积告警为既有现象，非失败）：**过**
- `npm run check:routes` → 七条路由全可达、默认路由 = 备课会话：**过**

**新建/改动文件**：

- 改：`frontend/src/areas/artifacts/VersionTimeline.tsx`（唯一代码改动）
- 改：本票文件（勾选 + 交付记录）

**逐项核对说明**：

- 「版本树关系（parent 衍生连线/标注）」以**标注**形态满足：展开后每个版本行显示
  「由第 N 版衍生」（`narrowing.parentLabel`），孤儿 parent 显示「由更早的一版衍生」。
- 「展开一次后该组保持展开」为组件存续期内的交互态（数据重取不影响）；离开生成物区再回来
  回到默认折叠——这正是「纯前端交互态，不入库、不进 URL」的口径。
- `GenerationPreview` 零改动（不在本票 Ownership，且行为符合票面要求）。

**遗留问题**：

- 前端无单测框架（spec 测试决策把前端验收钉在三件套门上），本票未引入测试框架，
  折叠交互的正确性靠门禁 + 人工核对；若后续引入 vitest 可为「深链自动展开 / 教师表态优先」补组件测试。
- npm install 的 audit 告警（6 条）为既有现象，未处理（非本票范围）。

【Ownership】
- 可改：`frontend/src/areas/artifacts/`（`VersionTimeline.tsx`、`SessionVersionCenter.tsx`、
  `ArtifactsSidebar.tsx` 如需）
- 禁区：`queries.ts` 的 query key 结构与端点（数据契约不动）；后端任何文件

【约束】视觉硬标准 `docs/style/minimalist-flat.md`：折叠箭头/展开态零阴影零渐变，
border-2 border-black、rounded-none、hover 黑白反色；文案中文全角标点；
版本用语遵守 CONTEXT.md §3（禁止「旧版本被覆盖」类表述）。
