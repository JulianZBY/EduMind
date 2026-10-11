# 12: 知识图谱重做：React Flow 思维导图（缩放/折叠/按学科下钻）

**What to build:** 教师打开知识图谱区，得到一张**可任意缩放、可折叠展开、可按学科下钻**的
思维导图：父子包含做树骨架，前置依赖/推导关系/相关关联以不同线型叠加在同一画布上（关系不丢）；
点入某个学科进入该学科知识点的子图，可返回全图。mermaid 平铺退场。

**Blocked by:** 08（下钻的分类维度 = 学科，由 08 供数）、11（布局库选型直接采信 spike 结论）

**Status:** done

选型（教师已拍板）：**React Flow（@xyflow/react）+ 树布局**；布局库以 11 票结论为准。
被否决：markmap / mind-elixir（严格树形，非树关系放不进去——四种关系是产品骨架，ADR-0007）。

- [x] 画布：滚轮缩放、拖拽平移、节点折叠/展开（折叠只藏子树，不删数据）、适应画布按钮
- [x] 四种关系同画布：父子包含=树边；其余三种=叠加线型（如虚线/不同箭头），图例可见；
  数据全部来自既有四种关系，不新增类型（ADR-0007）
- [x] 按学科下钻：点学科（类别）进入子图，可返回全图；入口直白
- [x] 知识点详情抽屉保留：点节点仍看内容/来源引用/关系
- [x] 风格：过 `docs/style/minimalist-flat.md` 自检清单——节点 border-2 border-black、
  rounded-none、零阴影零渐变、选中/悬停黑白反色、画布纯白
- [x] mermaid 从图谱区退场（先全局搜确认无他处引用，再移除依赖）
- [x] `npm run lint`、`npm run build`、`npm run check:routes` 全绿；数据→画布模型的转换纯函数
  （树骨架 + 叠加边的划分）有离线测试
- [ ] 教师配合视检：缩放/折叠/下钻手感与视觉（【收尾】教师执行；主观视觉判断不阻塞自动化验收）

【Ownership】
- 可改：知识图谱区前端、前端依赖清单（新增 React Flow 与布局库）、转换纯函数
- 禁区：后端任何文件（图谱数据契约不动；确需新端点另开票）；其他区的前端文件

【约束】百级节点不卡死：默认展开到第二层；无障碍交由 React Flow/Radix 内建能力，焦点可达；
界面用「学科」「知识点」「关系」等 CONTEXT.md 词汇。

## 交付记录（2026-10-11，分支 main，commit b8e0e60）

布局完全采信票 11 裁决：`elkjs/lib/elk.bundled.js` + ELK Layered（`direction='RIGHT'`、
nodeNode=18/betweenLayers=64/edgeNode=10），**只喂「父子包含」树边，叠加边绝不参与布局**；
elk worker 全局一份，异步布局带序号防重入（spike 说的 mermaid 同款模式）。

实现落点（全部在 Ownership 范围内）：

- `frontend/src/areas/knowledge-graph/graphModel.ts`（新）：转换纯函数——树骨架构建
  （第一个父胜出；自环/多父/成环/**端点被过滤掉**的父子边降级为叠加边，数据不丢）、
  学科虚拟根挂载（subject 为空归「未分类」）、折叠隐藏（只藏子树）、默认展开到
  **第二层知识点**（学科根是虚拟层不计入；第 3 层起先折着，百级节点不卡死）、
  elk 布局输入/输出适配、负坐标平移归零。零运行时依赖，`node --test` 可直接离线运行。
- `frontend/src/areas/knowledge-graph/graphModel.test.ts`（新）：10 例离线测试（树骨架/降级/
  学科根/初始折叠/折叠隐藏/叠加边可见性/重复边 id 去重/elk 适配）。Node ≥ 23.6 原生
  type stripping，零测试框架依赖；tsconfig 本就开着 `erasableSyntaxOnly`。
- `frontend/src/areas/knowledge-graph/GraphCanvas.tsx`（重写）：React Flow 画布——
  自定义节点（白底黑框直角、选中=强调色描边、悬停黑白反色、学科根粗体、有子树的知识点
  带 +/− 折叠按钮）、树边黑色粗实线直角折线、叠加边按 `relationStyle` 唯一配方
  （前置=黑实线/推导=黑虚线/相关=强调色虚线）、左下「适应画布」按钮、图例复用
  `RelationLegend`。数据引用一换（过滤/邻域/重拉）折叠即重置（render 期比对，无 effect 级联）。
- `frontend/src/areas/knowledge-graph/KnowledgeGraphArea.tsx`：点学科根=设 `?subject=`
  下钻（复用既有过滤机制，URL 即视图状态不变）；下钻态顶栏显示「已下钻到这个学科的知识点
  子图」+「返回全图」按钮；邻域/下钻中学科根不可点（避免状态交叉）。
- `frontend/package.json`：+`@xyflow/react@12`、+`elkjs@0.12`（票面授权新增）；
  +`"test": "node --test src/"`（离线测试的可跑入口）。
- 知识点详情抽屉、过滤下拉、邻域子图、URL 路由契约：原样保留，未动。

**mermaid 依赖未移除**（票面条件「先全局搜确认无他处引用」不成立）：冲突审核区的
`structureGraph.ts` / `StructureOutcomes.tsx` / `FlatMermaid` 仍在用；图谱区代码已零 mermaid
引用。票 11 遗留说明「elkjs 440KB gz 的成立前提是 mermaid 同票移除」因此不成立——图谱区
走 lazy.ts 懒加载不进首屏，冲突区仍用 mermaid 不增重；等冲突区有自己的退场票再一并移除。

跑过的命令与结果：

- `npm test`：10 pass / 0 fail（`node --test src/`）
- `npm run lint`（含禁用 class 扫描 + oxlint）：exit 0，零警告
- `npm run build`（含 check:classes + tsc -b + vite build）：exit 0
- `npm run check:routes`：七条路由全绿
- 后端 `uv run pytest -q`：565 passed（未动后端，确认无破坏）

双轴评审（Standards/Spec 并行子代理）处置：修了节点 focus-visible 聚焦样式回退、
显式 `rounded-none`、「返回全图」入口直白化、展开层数口径（知识点第二层）、
重复叠加边 id 撞、过滤后端点缺失的父子边静默消失、边构造参数结队；判断性保留：
叠加边直线（无圆角不违反配方，且与树边折线形成视觉区分）、npm test script
（「有离线测试」的可跑入口）。教师视检一项按票面留待收尾，未勾选。

## 遗留/注意

- **教师视检未做**（票面收尾项）：缩放/折叠/下钻手感与视觉；当前库内无知识点数据
  （02 清空后教师未再上传），视检需先有带学科归类的真实资料。
- mermaid 依赖保留原因如上；移除依赖的前置是冲突审核区先退场（可另开票）。
- elk 布局失败（worker 异常）时兜底：全部节点叠原点显示，图仍可点可拖，无层次——
  代码内有 `shortcut:` 注释标明升级时机。
