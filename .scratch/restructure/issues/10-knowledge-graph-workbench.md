# 10: 知识图谱工作台

**What to build:** 教师以可视化形式查看知识图谱：前端从图谱数据自行生成 mermaid 并按扁平主题渲染（白底黑框直角节点、直角折线），按学科 / 章节过滤，四种关系（前置依赖 / 父子包含 / 推导关系 / 相关关联）用黑与强调色的实线 / 虚线区分；点击知识点节点弹出详情（内容 / 难度 / 来源引用）；可从选中节点展开邻域子图（后端补过滤、节点详情、邻域取子图接口）。

**Blocked by:** 04 前端基座

**Status:** ready-for-agent

- [x] 图谱渲染符合风格文档的 mermaid 扁平主题配方，一眼可辨为 Minimalist Flat
- [x] 学科 / 章节过滤后节点与边正确收缩
- [x] 节点详情抽屉展示知识点内容 / 难度 / 来源引用
- [x] 邻域展开以选中节点为中心正确取子图（接口行为有 HTTP 缝测试）

## 交付记录

**分支**：`JulianZBY/issue-10-knowledge-graph-workbench`（本工作树当前分支；未 push、未开 PR、未 merge）
**主提交**：`f8cd224` · `feat(10): 知识图谱工作台`（验收项勾选与本节记录都在这个提交里；收尾的哈希补充见 `git log` 顶部）

### 一、跑过的命令与结果

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv sync` | 成功（本工作树原先没有 `.venv`；`.venv` 被 `.gitignore` 忽略） |
| `cd frontend && npm install` | 成功（新增依赖只有 `mermaid@^12.0.0` 一个） |
| `cd backend && uv run pytest -q` | **192 passed**（既有 181 + 本票新增 11 条 HTTP 缝测试） |
| `cd backend && uv run ruff check .` | `All checks passed!` |
| `npm run gen:api` | 成功：19 条路径 / 19 个操作（既有 16 + 本票 3 个新端点）；`openapi/openapi.json` 与 `src/api/generated/*` 已刷新 |
| `npm run lint` | 通过：`[check:classes] 64 个文件，10 条规则零违规` + oxlint 零告警 |
| `npm run build` | 通过：`check:classes` + `tsc -b` + `vite build`（mermaid 走动态 import，单独分块；主包 463 kB） |
| `npm run check:routes` | 通过：七条路由可达 + 默认路由 = 备课会话（票 04 的自检没被本票改动打破） |
| jsdom 真渲染验证（临时脚本，见第五节） | 两轮共 30 余项断言全过：真 mermaid 解析 + 真渲染 + 产出 SVG 逐项核对风格清单；**第二轮抓到并修掉一个真 bug**（见第五节末） |

### 二、后端（`/api/v1`，全部 `tag=知识图谱`）

| 端点 | 语义 | 变化 |
| --- | --- | --- |
| `GET /knowledge/graph` | 全图；带上 `subject` / `chapter` 即可选过滤，**过滤后连线随之收缩**（只留两端都在结果集里的关系，不留悬空关系） | 在既有端点上**追加可选 query 参数 + `response_model`**（见第六节取舍①）：不带参数时行为与语义与改造前完全一致 |
| `GET /knowledge/nodes/{node_id}` | 知识点详情：内容 / 学科 / 章节 / 难度 / 重要度 / **来源引用**（`sources[].doc_id` + 资料名）；不存在 = `404` | 新增 |
| `GET /knowledge/nodes/{node_id}/neighborhood` | 邻域子图：`nodes` 以中心知识点开头、其余按 BFS 访问序，`edges` 每条关系只出现一次；`max_depth` 1–3（默认 2，越界 `422`）；中心不存在 = `404` | 新增 |

- 图谱逻辑住 `backend/app/knowledge/graph.py`（新增 `node_summary` / `edge_ref` / `filter_graph` / `source_refs` / `node_detail` / `subgraph`，既有 `traverse` / `neighborhood` / `save_knowledge` 未动）。
- **既有三个知识库端点（`/knowledge/search`、`/knowledge/retrieve`、`/knowledge/web-search`）的注解与语义一字未改**（只有 `knowledge.py` 的 import 行按需增删）。
- 没建新表、没加新字段（`db/models.py` 未动）。
- HTTP 缝测试 `backend/tests/test_graph_workbench.py`（11 条）：按学科 / 按章节 / 学科+章节 / 空结果 / 不带过滤 = 全图 / 详情字段与来源引用 / 详情 404 / 一跳与两跳邻域（中心在首位、边去重、默认跳数）/ 邻域 404 与 422 / 叶子节点邻域。只断言响应与数据，不断言内部函数调用。

### 三、前端：可复用图谱组件（票 11 的复用入口）

组件住 `frontend/src/components/graph/`（**只新增文件，未改既有组件**）：

| 文件 | 作用 |
| --- | --- |
| `flowchart.ts` | 第 8 节配方与关系的**唯一实现**：主题 init、线型表、源码生成、转角还原 |
| `FlatMermaid.tsx` | mermaid 渲染器（扁平皮肤）：加载态 / 失败态 / 节点点击 |
| `RelationLegend.tsx` | 四关系图例（线型与颜色直接读线型表，与画布同源） |
| `FlatLoading.tsx` | 直角进度条加载态（图谱相关界面共用） |
| `index.ts` | 出口：`import { FlatMermaid, RelationLegend, FlatLoading, buildFlowchartSource, FLAT_THEME_INIT, RELATION_STYLES, sharpenLinkCorners, mermaidNodeIdFromDomId, ACCENT_COLOR, flatThemeSource, relationStyle } from '../../components/graph'` |

**用法（票 11 的结构冲突图示照抄即可）**：

```tsx
// 1) 只渲染一段自己的 mermaid 源码：主题由 FlatMermaid 自动补（第 8 节配方）
<FlatMermaid source={'flowchart LR\n  cur["图谱现状"] --> next["接受新"]'} label="结构冲突：接受新" />

// 2) 想复用关系线型 / 直角折线 / 折叠节点点击，就用生成器（节点名 n0、n1…与业务 id 的对应关系随源码返回）
const { source, nodeIdByMermaidId } = buildFlowchartSource(
  [{ id: 'old', label: '旧知识点' }, { id: 'new', label: '新知识点' }],
  [{ from: 'old', to: 'new', relation: '前置依赖' }],
)
<FlatMermaid source={source} onNodeClick={(mermaidId) => setSelected(nodeIdByMermaidId[mermaidId])} />
```

`buildFlowchartSource(nodes, edges, options)`：`nodes = { id, label, highlighted? }[]`、`edges = { from, to, relation }[]`、`options = { direction?: 'TB' | 'LR', showRelationLabels?: boolean }`（默认 `TB`，知识点标题较长；关系名默认不写，四种关系已由线型区分）。

### 四、知识图谱区（`frontend/src/areas/knowledge-graph/`）

- `index.tsx`：两条子路由（`index` 与 `:knowledgePointId`）**指向同一个组件**，所以「看全图 ↔ 选中知识点」之间跳转不会重挂画布、不重渲染一遍图；区路径由 `KNOWLEDGE_GRAPH_PATH` 单点定义。
- `KnowledgeGraphArea.tsx`：过滤条（学科 / 章节下拉用 Radix `DropdownMenu`，当前项用强调色方点标记）+ 画布 + 抽屉接线。
- `GraphCanvas.tsx`：数据 → `buildFlowchartSource` → `FlatMermaid`，底部图例与「N 个知识点 · M 条关系」。
- `KnowledgePointDrawer.tsx`：内容 / 难度（含重要度）/ 来源引用，以及「N 跳」展开邻域与「返回全图」。
- `queries.ts`：三个端点的 TanStack Query hooks + `collectFacets`（过滤选项只从**全图**汇总，否则过滤后选项会跟着缩、回不到别的学科）。
- **视图状态全部住在 URL**：`?subject=` / `?chapter=` 过滤、`?depth=` 邻域跳数、路径上的知识点 id 是选中的节点（抽屉开合）。刷新、回退、分享链接都还原同一屏；过滤切换用 `replace` 不往历史里堆。
- 空 / 加载 / 失败三态：空图分「图谱还是空的」与「这个范围里没有知识点（+ 清除过滤）」；失败用强调色边框 + 文案 + 重试；加载用文字 + 直角进度条，都不退回浏览器默认样式。

### 五、渲染合规证据（风格文档第 7 / 8 节）

第 8 节配方逐项照抄进 `FLAT_THEME_INIT`（`theme: base` + 8 项 themeVariables：白底 / 黑字 / 黑框 / 黑线 / 白填充 / 自托管字体）。**配方之外做了四处必要补充**（都在文件头写清理由）：

1. `look: classic`：mermaid 12 新的 neo 观感会给节点叠投影滤镜与渐变描边，与第 8 节「禁用…阴影主题」「零阴影 / 零渐变」直接冲突，必须关掉；
2. `themeCSS` 把节点描边钉成 **2px**：base 主题默认 1px，而第 8 节要求「黑边（2px）」；
3. `themeCSS` 钉住图内字体：配方里的 `fontFamily` 会被 mermaid 的**指令净化器**清空——它的取值白名单不含连字符，而 `sans-serif` 带连字符；
4. `sharpenLinkCorners()`：mermaid 12 的流程图渲染**固定**在拐点画 5px 倒角（`flowchart.curve` 的 step / linear / basis 等取值与 `linkStyle … interpolate` 实测都不改变输出，配置项在这条路径上是死的），第 8 节要求「直角折线」且风格文档要求零圆角，故把倒角命令 `Q 拐点 终点` 无损还原成 `L 拐点 L 终点`——只动连线（`flowchart-link`）的 `d`，节点形状一律不碰。

**键盘可达**：mermaid 只画图形、不带焦点语义，`FlatMermaid` 渲染后给每个节点补上 `tabindex="0"` + `role="button"`，并在容器上接 Enter / 空格触发同一个「打开知识点详情」回调；聚焦样式写在主题 `themeCSS` 里（强调色描边，不用浏览器默认蓝圈）。

线型与颜色严格按第 8 节表格：前置依赖 `-->` 黑实线、父子包含 `==>` 黑粗实线、推导关系 `-.->` 黑虚线、相关关联 `-.->` 强调色虚线。**故意不写 `linkStyle default stroke:#000000`**：mermaid 会把 linkStyle 的颜色拼在每条连线样式串最前面，而箭头 marker 取的是**第一个** stroke，写了会让「相关关联」变成强调色线 + 黑色箭头（见第六节取舍②）。

证据：临时脚本（跑完即删，未入库）在 jsdom 里用**真 mermaid** 解析 + 渲染 `buildFlowchartSource` 的产出，逐项断言：配方 8 项色值与 base 主题、2px 黑边、图内字体、聚焦样式；四种关系线型逐行比对第 8 节表格；`linkStyle 3 stroke:#ff3366`（相关关联）与节点命中 `classDef`；渲染出的 SVG 里节点观感 = classic、元素上无 filter、节点 `rx` 全 0、`stroke-width:2px`、连线/箭头同为强调色的只有 1 条、虚线关系 2 条、转角还原后连线只剩 `L` 且原拐点全部保留、节点形状逐字节未变、4 个节点都能 Tab 到并能从 domId 反解出知识点；另覆盖空图 / 单节点 / 关系名标签 / 横向布局 / 引号标题都能被解析。

> **第二轮验证抓到的真 bug**：mermaid 12 画出来的节点 id 是 `<图 id>-flowchart-<节点名>-<序号>`（带本次渲染的图 id 前缀），而最初的反解正则从串首匹配 `flowchart-`，于是点节点会静默无反应。已改成匹配末段（`(?:^|-)flowchart-(.+)-\d+$`）并在真渲染的 SVG 上锁定该行为——这条只能靠真渲染发现，纯看代码不会露。

第 7 节清单自检：无阴影 / 无渐变 / 无灰底 / 无半透明底；容器均 `border-2 border-black` + `rounded-none`；只用黑、白、`#ff3366`（强调色只出现在当前项标记、命中描边、关系线与失败边框）；悬停黑白反色；四态齐全且聚焦为 `outline-2 outline-offset-2`；过渡只有 `transition-colors duration-150`；无循环动画（加载态是静态直角进度条）；下拉用 Radix；字体自托管、图内字体同样钉成 Noto Sans SC / Space Grotesk；无 emoji。

### 六、取舍与偏离（都写清，不静默绕过）

1. **过滤做在既有 `GET /knowledge/graph` 上（可选 query 参数 + `response_model`），不是再加一个并列端点。** Ownership 写的是「`knowledge.py` 仅追加新端点」，而票面写的是「补过滤」；选前者的理由：不过滤时行为与语义完全不变（向后兼容），且票 04 特别指出该端点缺 `response_model` 导致前端类型是 `unknown`——前端要用的全图/过滤图必须是带类型的同一个端点，否则会留一个「与过滤端点重复且前端不用」的旧端点。**未动**三个知识库端点的注解与语义。
2. **不写 `linkStyle default stroke:#000000`**（见第五节）：黑本来就是主题默认值，写了反而会让强调色连线的箭头变黑。
3. **`GraphNode` 追加 `subject` / `chapter` 两个字段**：过滤选项必须从全图汇总，节点摘要不带这两个字段前端就只能再开一个端点或猜数据。
4. **来源引用只到资料粒度**：模型里只有 `source_docs`（资料 id 列表），没有分块级溯源，故接口如实返回资料名 + 资料 id，不假装能指到「第几段」（CONTEXT 的「来源引用」理想粒度是段，这里受数据模型限制）。
5. **查看态与过滤态用两个查询**（全图用于选项、过滤图用于画布）：数据量小时两条查询无感，换来的是过滤选项永远稳定；两者在不过滤时是同一条 query（同一个 key）。
6. **依赖只加 `mermaid`**：mermaid 体积大，故组件里用动态 `import()`（不进主包，服务端渲染也不会加载它）。
7. **图谱组件没有并进 `components/ui/index.ts`**：那个出口的注释说「新增组件请同时更新本文件」，但图谱组件不是 UI 基座（不提供四态交互皮肤），且本波 09/12 也开分支——动共享出口会平白制造合并冲突；改用图谱自己的出口 `components/graph/index.ts`（新增目录，共享文件一行未动）。

### 七、遗留问题（本票范围外或需后续票）

- **画布不做分页 / 虚拟化**：`GET /knowledge/graph` 一次返回全部知识点与关系，图谱很大时渲染会吃力；邻域接口的 `max_depth` 上限 3 是刻意收的（防止一拉一大片）。
- **未做浏览器真点验证**：本票的渲染证据是 jsdom 真渲染 + 断言（无浏览器可用）；真机五条主路径的冒烟留给票 14/08。
- 节点详情抽屉暂无「跳到题库 / 冲突审核」的联动（跨区跳转不在本票范围）。
- 覆盖率提示：`pi-lens` 的 opengrep/typos 运行器在本环境静默，故静态检查结果不是「全清」证明，只能说没有报告问题。
- 本机 `frontend/node_modules` 里残留了验证用的 `jsdom`（用 `npm install --no-save` 装过）：`package.json` / `package-lock.json` 已从备份还原、**未入库**（`rg jsdom frontend/package-lock.json` 零命中），下次 `npm ci` 会自然清掉。
