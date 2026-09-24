# 04: 前端基座

**What to build:** 新前端的骨头先立起来：六区（备课会话 / 知识库 / 生成物 / 知识图谱 / 冲突审核 / 题库）+ 设置的导航路由（默认落在备课会话区），Minimalist Flat 基线组件（按钮 / 输入 / 卡片 / 标签 / 弹层 / 抽屉 / 轻提示，交互原语用 Radix），服务端状态与界面状态接线，从后端 OpenAPI schema 生成 TS 类型的管线，禁用类扫描脚本。各区为空壳但可导航、风格到位——这是把旧单文件界面替换掉的第一步。

**Blocked by:** 01 规范与决策文档基线; 02 能力注册统一

**Status:** done

- [x] 七条路由可达，默认路由 = 备课会话区
- [x] 基线组件逐项通过风格文档自检清单（零阴影 / 零渐变 / 零灰底 / border-2 border-black / rounded-none / 悬停黑白反色）
- [x] 接口类型全部由 OpenAPI 生成，仓库无手抄接口类型
- [x] 禁用类扫描脚本挂入 lint/build，能拦截违规 class
- [x] 骨架采用工作台密度

## 交付记录

**分支**：`JulianZBY/issue-04-frontend-foundation`（本工作树当前分支；未 push、未开 PR、未 merge）
**主提交**：`601a74c` · `feat(04): 前端基座（七路由 + 扁平组件库 + 类型管线 + 禁用类扫描）`
**收尾提交**：`index.html`（`lang="zh-CN"` + 标题）与本节记录在同一提交里，见 `git log` 顶部。

### 一、跑过的命令与结果

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv sync` | 成功。本工作树原先没有 `.venv`，类型管线需要它；只读后端 schema，**没有改动 backend 任何文件**（`.venv` 被根 `.gitignore` 忽略） |
| `cd frontend && npm install` | 成功，依赖按 `package.json` 装齐（0 vulnerabilities；`npm audit` 的 4 条 high 见「遗留」） |
| `npm run gen:api` | 成功：16 条路径 / 16 个操作 → `openapi/openapi.json`；生成 `src/api/generated/{index.ts,types.gen.ts}` |
| `npm run gen:api`（连跑两次比对哈希） | 快照与生成物 SHA256 完全一致 → 幂等、可复现 |
| `npm run lint` | 通过：`[check:classes] 禁用 class 扫描通过：57 个文件，10 条规则零违规` + oxlint 零告警，exit 0 |
| `npm run build` | 通过：`check:classes` + `tsc -b`（无错）+ `vite build`（js 449.59 kB / gzip 143.12 kB；css 18.86 kB），exit 0 |
| `npm run check:routes` | 通过：7 个区匹配 + 逐条 SSR 渲染出对应区名 + 默认路由 `/` → `/lesson-prep`，exit 0 |
| `npm run dev -- --port 5199` 后逐条请求 | 10 条 URL 全部 `200` 且返回 SPA 入口（七条一级路由 + `/lesson-prep/session-abc` + `/no-such-area`） |
| 禁用类扫描正控 / 负控 | 见第五节 |

### 二、七条路由与默认路由（复现方式）

```bash
cd frontend
npm run check:routes    # 逐条匹配 + 逐条 SSR 渲染两段断言（不需要浏览器、不需要后端）
npm run dev             # 再按下面的表逐条访问 http://localhost:5173<路径>
```

| 路径 | 区 | 主区形态 | 子路由（选中对象可寻址） |
| --- | --- | --- | --- |
| `/lesson-prep` | 备课会话（默认） | 二级侧栏（会话列表）+ 主区对话轴 | `:sessionId` |
| `/knowledge` | 知识库 | 二级侧栏（资料列表）+ 主区详情 | `:documentId` |
| `/artifacts` | 生成物 | 二级侧栏（按会话分组）+ 版本中心 | `:artifactId` |
| `/knowledge-graph` | 知识图谱 | 主区直铺画布 | `:knowledgePointId` |
| `/conflicts` | 冲突审核 | 主区直铺队列（三类别标签页，`?category=definition|structure|common-sense`） | `:conflictId` |
| `/question-bank` | 题库 | 二级侧栏（题目列表）+ 主区详情 | `:questionId` |
| `/settings` | 设置 | 单页表单（编辑密度） | — |

**默认路由 = 备课会话区** 的三重证明：

1. `src/app/router.tsx` 里 index 路由 `loader: () => redirect(DEFAULT_AREA_PATH)`；`check:routes` 直接调用这个 loader，读回的 `Location` 就是 `/lesson-prep`（输出行：`✓ 默认路由 / 重定向到 /lesson-prep（实得 /lesson-prep）`）。
2. `DEFAULT_AREA_PATH === '/lesson-prep'`，且注册表硬校验「全站只能有一个 `isDefault`」——多一个少一个都会在启动时抛错（输出行：`✓ 全站只有一个默认区，且是备课会话`）。
3. dev server 起在 5199 端口后逐条请求十项 URL 均 200，其中 `/` 与未知地址都由 SPA 入口接管、再由路由落到 `/lesson-prep` 或 404 页。

### 三、扩展点（09/10/12/13 并行开发的接法）

一区一目录 `frontend/src/areas/<area>/`：

| 文件 | 责任 | 谁来改 |
| --- | --- | --- |
| `index.tsx` | 本区 `AreaModule`：`id / label / path / order / isDefault / tagline / routes` | 加区、改路由时 |
| `<Area>Area.tsx` | 本区界面（工作台或直铺）+ 区内占位内容 | 09/10/12/13 **主要在这里改** |
| `queries.ts` | 本区 TanStack Query 的 key 根与 hooks | 同上 |

汇总点只有一个：`src/areas/registry.ts` 用 `import.meta.glob('./*/index.tsx', { eager: true })` 自动发现，**文件里不含任何一区的内容**。

新增一区的确切步骤（不碰任何共享文件）：

1. `mkdir src/areas/<area>`；
2. 建 `<Area>Area.tsx`（界面）与 `queries.ts`（本区 query key 根，`export const xKeys = { all: ['<area>'] as const }`）；
3. 建 `index.tsx`，默认导出 `AreaModule`；其中顶层路由的 `id` 必须等于 `area.id`（注册表会校验，缺了就抛错），`order` 决定区级导航顺序；
4. 在 `scripts/check-routes.mjs` 的 `EXPECTED_AREAS` 里加一行（这是唯一需要动的地方，只为让自检知道期望七条之外的新区），跑 `npm run check:routes`。

**路由表、区级导航、注册表三处都不用改**——因为区级导航直接遍历注册表，路由表把各区的 `routes` 摊平。

服务端状态同理按区分文件（`queries.ts`，不塞进全局大文件）；跨组件界面状态在 `src/store/ui.ts`（zustand）；区内专属界面状态按需加 `src/areas/<area>/store.ts`。**一处改动同时要碰两个区的文件 = 接错了地方。**

### 四、基线组件四态核对（风格文档第 3 节）

| 组件 | 默认 | 悬停 | 聚焦（focus-visible） | 禁用 |
| --- | --- | --- | --- | --- |
| 按钮 `Button` | 白底黑字 `border-2 border-black`；accent 档 = `bg-[#ff3366]` + 黑字 | `hover:bg-black hover:text-white`（黑白反色） | `outline-2 outline-offset-2 outline-black` | 边框 2px→1px + `text-black/40` + 不响应指针 |
| 输入 `Input` | 白底黑字 `border-2 border-black`；`aria-invalid` 转强调色边框 | `hover:border-4`（边线加粗，见下方取舍②） | `outline-2 outline-offset-2 outline-black` | 边框 2px→1px + `text-black/40` + `cursor-not-allowed` |
| 卡片 `Card` | `border-2 border-black` + `rounded-none`，无装饰 | `interactive` 时整卡反色 | `interactive` 时 `outline-2` | `disabled`：1px 边线 + 文字弱化 |
| 标签 `Badge` | 三档：outline / solid（黑底白字）/ accent（强调色底黑字） | 传 `onClick` 时反色 | 同上 | 同上 |
| 弹层 `Dialog` | 面板 `border-2 border-black`；遮罩不透明、不模糊 | 关闭按钮反色 | 关闭按钮 outline-2 | 无禁用语义（Esc / 点外关闭由 Radix 承担） |
| 抽屉 `Drawer` | `border-l-2 border-black` 把面板与页面隔断 | 关闭按钮反色 | 关闭按钮 outline-2 | 同上 |
| 轻提示 `Toast` | `border-2` + 左侧 8px 色条（默认黑 / accent 强调色） | 整条反色（Child 用 `group-hover` 跟随） | 关闭按钮 outline-2 | 关闭按钮 |
| 标签页 `Tabs` | 白底黑字 `border-2`；当前项 = 反色 + 强调色左边线 | 反色 | `outline-2` | `data-disabled` 文字弱化 |
| 下拉 `DropdownMenu` | 条目白底黑字 | `data-highlighted` 反色（鼠标悬停与键盘高亮同一表达） | 同左 + 可见轮廓 | `data-disabled`：1px 边线 + 弱化 |

两处**显式取舍**（写清楚，不静默绕过风格文档）：

1. **输入框的悬停不做黑白反色，改成边线加粗（2px→4px，`border-box` 故不位移）。** 理由：文本输入框悬停变实心黑块会把刚输入的字盖住，反色在这里不可读；风格文档第 3 节的「悬停 = 黑白反色」是为按钮 / 选项 / 导航这类交互定的。
2. **禁用态用「边框 2px→1px + 文字降为 `text-black/40`」，没有用 `-webkit-text-stroke` 做字面「文字描边」。** 理由：中文笔画做描边后基本不可读；第 1 节明确允许灰度只作为**文字色**深浅（示例即 `text-black/60`），本实现的禁用态没有任何灰色**填充**，符合「禁用靠边线变细 + 文字弱化、不用灰底」的本意。若评审坚持字面描边，改动是组件基类各一行。

### 五、禁用 class 扫描（正控 / 负控都留了记录）

- 脚本：`frontend/scripts/check-forbidden-classes.mjs`，按风格文档第 6 节 **10 条正则**逐条实现，扫描 `frontend/src/**/*.{ts,tsx,css}`，逐行报告 `文件:行:列 + 规则号 + 命中片段`，命中即 `exit 1`。
- 挂载：`npm run lint` = `check:classes && oxlint`；`npm run build` = `check:classes && tsc -b && vite build`（构建流程同样拦得住）。
- **正控（真能拦，已自测）**：临时放 `src/__scan-selftest__.tsx`，含 `shadow-md` / `rounded-lg` / `bg-gray-100` / `transition-all` / `duration-300` / `text-green-600`：

  ```
  [check:classes] 禁用 class 扫描未通过（docs/style/minimalist-flat.md 第 6 节）：
    ✗ 规则 1 阴影 · src\__scan-selftest__.tsx:3:46 · 命中「shadow-md」
    ✗ 规则 2 圆角 · src\__scan-selftest__.tsx:3:19 · 命中「rounded-lg」
    ✗ 规则 4 灰度底色 · src\__scan-selftest__.tsx:3:30 · 命中「bg-gray-100」
    ✗ 规则 7 越界过渡 · src\__scan-selftest__.tsx:3:56 · 命中「transition-all」
    ✗ 规则 8 超时长动效 · src\__scan-selftest__.tsx:3:71 · 命中「duration-300」
    ✗ 规则 9 非强调彩色 · src\__scan-selftest__.tsx:3:84 · 命中「text-green-600」
  [check:classes] 共 6 处违规，58 个文件已扫描。
  ```
  `npm run lint` exit 1；`npm run build` 在第一步就 exit 1。
- **负控（不误伤）**：临时放只用 `shadow-none` / `rounded-none` / `transition-colors` / `duration-150` / `animate-spin` / `outline-2` / `bg-[#ff3366]` 的文件 → `[check:classes] 禁用 class 扫描通过：58 个文件，10 条规则零违规`，exit 0。
- 两个临时文件跑完即删（`Get-ChildItem src -Filter '__scan*'` 无结果）。

### 六、类型管线

```bash
cd backend && uv sync      # 一次性前置（本工作树已执行过）
cd ../frontend && npm run gen:api
```

- `npm run gen:api` = `npm run openapi:snapshot` + `npm run openapi:types`。
- **不需要先起后端服务**：`scripts/dump-openapi.mjs` 在 `backend/` 目录下跑 `uv run python -c "from app.main import app; json.dump(app.openapi(), ...)"`，只取 schema，不触发 lifespan、不建库、不开端口。
- 入库产物：`frontend/openapi/openapi.json`（schema 快照）+ `frontend/src/api/generated/{index.ts,types.gen.ts}`（TS 类型）。
- 只刷类型（不碰后端、不需要 uv）：`npm run openapi:types`。
- 仓库存量代码里确认无手抄接口类型：`rg "interface .*(Request|Response|Payload|Dto)" src --glob '!src/api/generated/**'` → 无命中（唯一命中项 `ApiCallOptions` 已改名，它是传输选项，不是接口形状）。旧 `src/types.ts` 里手写的 `Artifacts / WordData` 接口类型随旧界面一并删除。前端拿 URL 常量的方式也是从生成类型取，例如 `src/api/system.ts: const pingUrl: PingApiV1PingGetData['url'] = '/api/v1/ping'`。
- **现状提醒（给 06–13）**：后端 16 个操作里只有 6 个带 `response_model`（`/api/v1/chat`、`/exam/generate`、`/interactive/generate`、`/knowledge/search`、`/revise`、`/revise/word`），其余 200 响应在 schema 里是 `{}`，生成出来是 `unknown`（`/health`、`/documents`、`/conflicts`、`/knowledge/graph` 等）。前端因此**不去猜响应字段**（猜就等于手抄）；建议后端补 `response_model` 后重跑 `npm run gen:api`，前端 hooks 即可直接用真类型。

### 七、风格文档第 7 节自检清单

**形状与材质**

- [x] 无 `shadow-*`（除 `shadow-none`）、无 `drop-shadow-*`（扫描规则 1 零命中）
- [x] 无 `rounded-*`（除 `rounded-none`），且容器都写了 `rounded-none`
- [x] 无 `bg-gradient-*` / `from-*` / `via-*` / `to-*`（规则 3）
- [x] 无灰度底色（规则 4）与半透明底色（规则 5；注意 `text-black/60` 是文字色深浅，规则只禁 `bg-*` 半透明）
- [x] 每个容器与卡片都是 `border-2 border-black`（禁用态 1px 是第 1 节指定的禁用表达，非容器常态）

**色彩**

- [x] 界面只有黑、白、`#ff3366`（强调色一律写成 `bg-[#ff3366]` / `text-[#ff3366]` / `border-[#ff3366]`，可一次 grep 出全部使用点）
- [x] 强调色上没有任何非黑文字（accent 底一律 `text-black`）
- [x] 成功 / 失败 / 警告没有红绿蓝：服务不可达 = 强调色边框 + 文案；轻提示 accent 档 = 强调色左边条 + 文案

**交互与动效**

- [x] 悬停是黑白反色（按钮 / 导航 / 列表条目 / 标签页 / 下拉条目 / 轻提示 / 可交互卡片），无位移、无缩放、无阴影；输入框悬停见取舍①
- [x] 可交互组件覆盖默认 / 悬停 / 聚焦 / 禁用四态，聚焦可见且非浏览器默认蓝圈（全局 `:focus-visible` 兜底 + 组件级 `outline-2 outline-offset-2 outline-black`）
- [x] 过渡只用 `transition-colors duration-150`，无 `transition-all`（规则 7、8）
- [x] 无循环动画（`animate-spin` 仅允许用于加载指示器；本票界面里加载态用文案「探测中…」表达，没有骨架屏灰块）
- [x] 弹层 / 抽屉 / 下拉 / 标签页全部用 Radix 无头原语：Esc 关闭、焦点陷阱、键盘方向键由原语承担

**排版与密度**

- [x] 字体自托管（`@fontsource/noto-sans-sc` + `@fontsource/space-grotesk`，无外链 CDN，规则 10 零命中）
- [x] 数字与英文用 Space Grotesk（字体栈 `Space Grotesk` 在前、中文自动回落 `Noto Sans SC`）
- [x] 数据区工作台密度（区级导航 32px 行高、侧栏 `px-3 py-2`、贴边 `border-b-2`）；空状态 / 设置 / 404 用编辑密度（`max-w-md`/`max-w-xl` 单列窄容器、`py-8~12`、`text-xl` 标题）
- [x] 无 emoji 装饰；图标是统一线宽 2 的线性 SVG（`strokeWidth=2`、无填充、无彩色）

**图谱（仅知识图谱区与结构冲突图示）**

- [ ] 本票不实现图谱渲染：mermaid 扁平主题配方、四种关系线型、节点选中描边都由票 10（图谱区）/ 票 11（结构冲突终态图）落地——本票只留好了区与画布位（`/knowledge-graph` 主区直铺，主题色与字体已就位）

**流程**

- [x] 禁用 class 扫描零违规（已在 `npm run lint` 与 `npm run build` 中执行，且做过正控 / 负控自测）
- [x] 空数据 / 加载中 / 失败三态符合本清单：空数据 = 各区编辑密度空状态；加载中 = 顶栏「服务探测中」+ 抽屉「探测中…」（无灰块骨架屏）；失败 = 「服务不可达」用强调色边框 + 明确文案，不退化成默认样式

### 八、新增 / 改动文件清单

**新增（52 个文件，均在 `frontend/`）**

- 工具与产物：`scripts/dump-openapi.mjs`、`scripts/check-forbidden-classes.mjs`、`scripts/check-routes.mjs`、`openapi/openapi.json`、`src/api/generated/{index.ts,types.gen.ts}`
- 接线与外壳：`src/main.tsx`（重写）、`src/app/{AppShell,AppHeader,AreaRail,ServiceStatusDrawer,AboutDialog,NotFoundPage,providers,queryClient,router}.tsx|ts`、`src/store/ui.ts`、`src/lib/cn.ts`、`src/api/{client,system}.ts`
- 基线组件：`src/components/ui/{Button,Input,Field,Card,Badge,EmptyState,Dialog,Drawer,Toast,useToast,Tabs,DropdownMenu,icons}.tsx|ts`、`src/components/ui/index.ts`
- 布局：`src/components/layout/{Workbench,SidebarNote,AreaStub}.tsx`
- 七个区：`src/areas/types.ts`、`src/areas/registry.ts`、`src/areas/<area>/{index.tsx,<Area>Area.tsx,queries.ts}` × 7 = 21 个文件（设置区只有 `index.tsx` + `SettingsArea.tsx` + `queries.ts`，无子路由）
- 样式与配置：`src/index.css`（重写为 Tailwind v4 主题）、`vite.config.ts`（+ `@tailwindcss/vite`）、`package.json`（依赖与脚本）、`index.html`（`lang="zh-CN"` + 标题）、`frontend/AGENTS.md`（命令口径 + 区目录约定）

**删除（旧单文件界面整体退场）**

- `src/App.tsx`（848 行）、`src/App.css`、`src/sessionStore.ts`（localStorage 会话）、`src/types.ts`（手写接口类型）、`src/assets/{hero.png,react.svg,vite.svg}`、`public/icons.svg`

**未改**：`backend/**`（只读 schema 生成快照）、`docs/**`、`CONTEXT.md`、`.scratch/**` 里非本票文件。

### 九、遗留问题

1. **后端多数 200 响应没有 schema**：16 个操作只有 6 个带 `response_model`，`/health`、`/documents`、`/conflicts`、`/knowledge/graph` 等生成出来是 `unknown`。不是前端能修的（属后端票），补完重跑 `npm run gen:api` 即可。这会影响 06–13 对响应体的直接使用（现在只能先拿 `unknown` 再在 hooks 里做收窄）。
2. **字体体积**：中文字体只引了 `chinese-simplified` 400/700 两个子集，但 fontsource 的 `@font-face` 同时声明 woff2 与 woff，`dist` 里因此多出约 3 MB 的 woff 兜底文件；确需瘦身可手写 `@font-face` 只留 woff2。
3. **`@hey-api/openapi-ts`（dev-only 代码生成器）带来 4 条 npm audit high**（传递依赖 `js-yaml`、`@hey-api/json-schema-ref-parser`），不进运行期产物；升级该工具即可消除。选它而不选 `openapi-typescript` 的原因：后者 peer 要求 `typescript ^5`，本仓库是 TS 6。
4. **没有真浏览器验证**：本票的证据是 `check:routes` 的 SSR 渲染断言（逐条渲染出区名 / 选中对象 / 404 文案）+ dev server 逐条 200。真浏览器冒烟是票 14 的范围（本机未安装 Playwright 浏览器，本票不引入依赖）。
5. **设置区是只读骨架**：控件全部 `disabled`，读写接口接入（票 13）后才开放；届时 `src/areas/settings/queries.ts` 里长 hooks，界面文件不动路由注册。
6. **冲突三类别只有形态没有检测**：结构冲突与常识存疑的检测逻辑尚未实现（ADR-0004），本票在标签页文案里明确写了「检测尚未实现，本区只呈现裁决形态」，未承诺能自动发现（CONTEXT 第 6 节文案纪律）。
7. `backend/.venv` 是本次为跑通类型管线而 `uv sync` 生成的（在 `.gitignore` 内，不影响仓库）；后续会话重跑类型管线无需再装。

## 协调者复核

**结论：通过（两处风格偏离与一项后端缺口已提交用户裁决）。** 复核人 = 协调者（主代理），2026-09-24。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| 七条路由可达、默认 = 备课会话 | 读 `src/areas/registry.ts`：`import.meta.glob('./*/index.tsx')` 自动汇总；七个区目录就位；`npm run check:routes` 逐条渲染断言 | 通过 |
| 基线组件过风格自检清单 | 逐项核对交付记录第四节四态表；组件均 `border-2 border-black` + `rounded-none` | 通过 |
| 接口类型由 OpenAPI 生成 | `npm run gen:api`（dump FastAPI app、不起后端）；无手抄类型 | 通过 |
| 禁用类扫描挂入 lint/build | **协调者突击检查**：向 `src/areas/lesson-prep/` 注入含 `shadow-md`/`rounded-lg`/`bg-gray-100`/`transition-all` 的探针文件 → `npm run lint` **exit 1**（4 处命中，规则号与行列均报出）；删掉探针后回到 exit 0 | 通过 |
| 工作台密度 | 列表/表格紧凑行高，空状态/设置用编辑密度 | 通过 |
| 构建 | 协调者亲跑 `npm run lint`（57 文件零违规）+ `npm run build` 成功；工作树干净 | 通过 |

**为并行开发留的缝（本次编排的关键收获）**：一区一目录 + `import.meta.glob` 自注册，使票 09/10/12/13 能在各自分支上并行落地而**不需要改任何共享文件**——本波四张票的并行与合并因此成立。

**两处风格偏离（提交用户裁决，结论：接受）**：① 输入框悬停 = 边线加粗（反色会盖住输入内容）；② 禁用态 = 边线 2px→1px + `text-black/40`（中文文字描边不可读）。
协调者已把两条例外**写进 `docs/style/minimalist-flat.md`**（第 1 节禁用态定义、第 3 节悬停例外、第 7 节自检清单同步，commit `c14bea7`），使文档与现实一致，后续 7 张前端票的 DoD 不再悬空。

**遗留去向**：① 「16 个操作只有 6 个带 `response_model`」→ 按用户裁决写入票 13 与后续票的约束；② 真浏览器冒烟（本机无 Playwright）→ 票 14；③ `@hey-api/openapi-ts` 带来 4 条 dev-only npm audit high → 票 14 收口时评估升级。

- **合并点**：`9468fc0`（`merge(04)`）；`frontend/` 与分支逐步一致。
- **状态迁移**：`ready-for-agent` → `done`。
