# 05: 生成物区版本时间线分组折叠

**What to build:** 教师打开生成物区的版本时间线，看到的是**按生成物分组**的列表：默认只展开
每类生成物的**当前版本**，历史版本与「由哪一版衍生」收起、点开才见。一眼看到的是「现在可用的是
什么」，不是全部历史。不删任何版本（全版本留痕口径不变，CONTEXT.md §3）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 时间线按 `artifact_type` 分组（课件/教案/提纲/试卷/互动内容），组内默认折叠到当前版本
- [ ] 展开组后可见全部版本与版本树关系（parent 衍生连线/标注）；历史版本仍可回看、下载、作基线
  （既有能力不回退）
- [ ] 备课会话区右侧面板（`GenerationPreview`）行为不变：仍只显示当前版本 +「共 N 版」入口
- [ ] 折叠状态是纯前端交互态，不入库、不进 URL（深链仍直达具体版本）
- [ ] `npm run lint`、`npm run build`、`npm run check:routes` 全绿；七条路由可达不回归
- [ ] 教师视角核对：折叠时看不到「第 1 版…第 N 版」全部平铺；展开一次后该组保持展开（会话内交互态）

【Ownership】
- 可改：`frontend/src/areas/artifacts/`（`VersionTimeline.tsx`、`SessionVersionCenter.tsx`、
  `ArtifactsSidebar.tsx` 如需）
- 禁区：`queries.ts` 的 query key 结构与端点（数据契约不动）；后端任何文件

【约束】视觉硬标准 `docs/style/minimalist-flat.md`：折叠箭头/展开态零阴影零渐变，
border-2 border-black、rounded-none、hover 黑白反色；文案中文全角标点；
版本用语遵守 CONTEXT.md §3（禁止「旧版本被覆盖」类表述）。
