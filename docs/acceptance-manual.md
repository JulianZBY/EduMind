# 人工验收手册

**这份手册只写「只有人能做的事」**：真浏览器逐区点选、真实云端 Key 下的联通性、人眼判断的视觉项。

- 机器能覆盖的部分**不在这里重复**：后端契约与行为测试（`uv run pytest -q`）、
  前端 lint / 构建 / 禁用 class 扫描（`npm run lint` / `npm run build` / `npm run check:classes`）、
  stub 模式全链路冒烟（附录 A，需要用你本机的端口跑一遍，但没有「点选判断」）。
- 依据：`CONTEXT.md`（术语，判断文案对不对的唯一依据）、`docs/architecture.md`（应有的形态）、
  `docs/api/**`（协议语义）、`docs/style/minimalist-flat.md`（视觉硬标准）、`docs/adr/**`（决策）。

> 为什么必须由人做：本仓库不装 Playwright（无浏览器自动化基建，见 `spec.md`「范围外」），
> 真实 Key 也不该进仓库。这两件事的验收只能由人拿着真浏览器与真 Key 走一遍。

---

## 0. 准备

### 0.1 起服务（两条命令，端口固定 8000 / 5173）

```bash
# 终端 1：后端（默认 stub 模式：不配任何 Key 也能全链路跑）
cd backend && uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 2：前端
cd frontend && npm install
npm run dev
```

浏览器打开 <http://localhost:5173>。

**预期现象**：右上角没有报错提示；`curl http://localhost:8000/health` 返回
`{"status":"ok","app":"EduMind","llm_provider":"stub"}`；`http://localhost:8000/docs` 打得开。

**失败怎么判断**：
- 页面白屏 / 顶栏出现连接异常 → 后端没起或端口被占（`/health` 直接打不通）；
- `/health` 通了但页面数据全空 → 看浏览器 Network 面板：4xx 是契约问题，5xx 看后端控制台堆栈；
- 前端起不来 → `node -v` 是否 ≥ 18、`npm install` 是否真的跑完（本仓库 `npm run dev` 不依赖后端先起）。

### 0.2 两种模式，验收范围不同

| 模式 | 怎么进入 | 能验收什么 |
| --- | --- | --- |
| **stub 模式**（默认） | 不配任何 Key | 链路、界面行为、导航、状态跟进、版本留痕。**内容不是真的**，且澄清回复 / 冲突队列等分支走不到（见 `docs/api/stub-mode.md`「走不到的分支」） |
| **真实 Key** | 设置页填 Key（或 `backend/.env`） | 上面全部 + 真实解析与生成质量、澄清追问、冲突检测 |

第 1 节在两种模式下都能做（走不通的分支已在各条目里标注）；第 2 节必须真实 Key。

### 0.3 建议先准备一批资料

放在一个本地目录里，第 1 节反复要用：

- 一份有文本层的 PDF（讲义类最好，含小标题）；
- 一份 Word（`.docx`）；
- 一张图片（板书 / 截屏）；
- 一段短视频（**含语音更好**，用来验证录音转写之外的视频抽帧路径）；
- 一段录音（`.mp3` / `.m4a`）。

---

## 1. 真浏览器逐区点选

导航栏顺序（URL 即路由）：**备课会话 `/lesson-prep`（默认落脚区）→ 知识库 `/knowledge` →
生成物 `/artifacts` → 知识图谱 `/knowledge-graph` → 冲突审核 `/conflicts` → 题库 `/question-bank` → 设置 `/settings`**。

**通用失败判定**：任何一区出现「接口暂时不可用 / 取不到」的空状态时，先看浏览器 Network 里那一条请求的
状态码——`4xx` 多半是前端传参与契约不一致，`5xx` 看后端控制台。空数据导致的空状态**不是**故障
（各区空状态文案不同，`题库`/`生成物`在没生成过东西时本来就是空的）。

### 1.1 备课会话

| 步骤 | 预期现象 | 失败怎么判断 |
| --- | --- | --- |
| 打开 `/lesson-prep`，点「新建备课会话」，不填标题直接确认 | 侧栏出现一条会话，标题是「新的备课会话」 | 弹层确认后侧栏没动 = 创建失败（看 Network 的 `POST /api/v1/sessions`） |
| 在对话轴输入「给初二讲一次函数，40 分钟」（回车发送） | 出现一条教师气泡 + 一条助手回复 | 助手回复里出现「[stub] 收到你的消息…」= 意图解析没命中 stub 场景（stub 下应返回完整 TCP 意图，属已知口径） |
| **stub 下**：回复是**生成回复**（列出 PPT 页数、Word 教案、提纲与命中的来源文档） | 这是 stub 的固定口径：意图要素齐全 → 不再追问 | 若期望看到追问，说明你在验「澄清回复」——它在 stub 下走不到，见下一条 |
| **真实 Key 下**：先说一句信息不全的话（如「备课」） | 回复是**澄清回复**（追问主题 / 时长 / 风格 / 重点），不带生成物 | 直接出生成物 = 意图解析把缺失要素补全了或模型没按 JSON 返回，看后端日志里两次 LLM 调用的原始输出 |
| 把追问粒度从「标准」改成「精细」再发一轮 | 精细档追问的要素更多（时长 / 风格 / 目标 / 重点 / 互动 / 方法） | 粒度没变 = 会话 PATCH 失败（`PATCH /api/v1/sessions/{id}`） |
| 在侧栏点「参考资料」勾选一份已完成的资料，再发一轮 | 生成回复里出现「本次命中的来源文档：<你的文件名>」 | 没有来源 = 该资料仍「处理中」/「失败」（勾不上），或检索真的没命中（把资料标为参考资料会加权） |
| 直接上传一份文件（对话轴旁的「上传教学资料」） | 上传后该资料自动进入本会话的参考资料 | 资料出现在知识库但没进本会话 = 上传绑定失败（看 `POST /documents/upload` 的 `session_id`） |
| 刷新浏览器（F5） | 会话、消息、生成结果全部还在 | 消息丢了 = 事实源没落在服务端（`GET /api/v1/sessions/{id}` 应有全部消息） |
| 换一个浏览器 / 无痕窗口打开同一地址 | 看到同一份会话列表与历史 | 只在本机有 = 事实源又回到了浏览器（`spec.md` 用户故事 6/7 的直接验收点） |
| 生成回复后看对话轴右侧 | 生成物并排预览（本次的课件 / 教案 / 提纲） | 右侧空 = 预览查询失败（`GET /sessions/{id}/artifacts`） |
| 侧栏搜索框输入标题片段 | 列表按标题过滤 | 不过滤 = 前端没把 `keyword` 传出去 |
| 侧栏每条会话的「更多操作」菜单→重命名 / 删除 | 重命名即时生效；删除弹**二次确认**，确认按钮是**强调色底**，删完列表少一条 | 删除没有二次确认 = 违反 `minimalist-flat.md` 第 3 节（破坏性动作硬标准） |

### 1.2 知识库

| 步骤 | 预期现象 | 失败怎么判断 |
| --- | --- | --- |
| 点「上传教学资料」，选一份 PDF | 列表立刻多一行，状态「处理中」 | 状态停不下来的前提是**没在跟进**（见下一条）；上传失败会直接给错误文案 |
| 不动手，等几秒 | 状态**自动**变「已完成」，不需要手动刷新 | 不自动变 = 前端没有轮询（`CONTEXT.md` 第 4 节：处理中应自动跟进） |
| **stub 下**上传图片 / 视频 | 都能走到「已完成」，分块内容带「[stub 视觉提取]」（视频另有「[帧 N]」） | 出现「失败」= 回归到票 15 修掉的老问题（视觉提取没有 stub） |
| 点开一份资料详情 | 看到状态、文件类型、分块数与分块正文 | 详情 404 = 上传接口返回的 id 没对上 |
| 对同一份资料点「标记为参考资料」 | 标记生效（再次打开仍是标记态），并给出「检索加权 / 溯源」的说明 | 标记丢 = PATCH 没落库 |
| 上传一份同名文件 | 生成两条独立记录（同名不覆盖） | 覆盖 = 文件名唯一性退化 |
| 上传一个不支持的扩展名（如 `.xyz`） | 上传本身成功（状态「处理中」），随后走到**「失败」**——解析器没有这个类型 | 永远停在「处理中」= 失败没被写回状态（后台任务的异常被呑了但没落终态） |

> 已知落差（不是本次验收的失败项）：资料列表**无分页**；详情只回**前 200 个分块**。

### 1.3 生成物

| 步骤 | 预期现象 | 失败怎么判断 |
| --- | --- | --- |
| 打开 `/artifacts`，侧栏按会话分组 | 每条会话下列出它的生成物数量 | 侧栏计数不对 = 版本列表端点没取到 |
| 点进有生成物的会话 | 版本时间线：每件生成物一组，组内「第 1 版 / 第 2 版…」升序，当前版本默认打开 | 组内乱序 = 版本号排序失效 |
| 点「第 1 版」再点「第 2 版」 | 预览内容随之切换，样式一致 | 切版本不刷新 = 预览没跟着 `version_id` 走 |
| 下载任一版本（含历史版本） | 浏览器保存文件，`.pptx` / `.docx` 能打开且内容对应那一版 | 下载到的是别的版本 = 版本与文件不是一一对应（`docs/api/artifacts.md` 的核心约定） |
| 对课件点「改一版」，写「把第二页的例子换成生活情境」，确认 | 产出一条**更高版本号**的新版本，`origin=修改`；旧版本仍在列表里、仍可下载 | 旧版本消失 = 违反 `CONTEXT.md` 第 3 节「全版本留痕」 |
| 对历史版本点「以这一版为基线修改」 | 新版本号比基线更高；再点基线版本，内容仍是修改前的 | 基线被覆盖 = 版本树没落 `parent_id` |
| 点「一键生成试卷」（弹层填主题 / 数量） | 生成试卷并提示已入题库；题型 / 题干 / 答案可看 | 题库里没有新题 = `bank_saved` 为 0（看响应） |
| 点「生成互动内容」（弹层填互动诉求） | 生成单文件 HTML5；下载/打开后**新标签页**能直接玩（按钮有反应） | 打开是下载而不是内联 = 少了 `inline=true` |
| 生成物预览与对话轴并排（回到 `/lesson-prep`） | 同一份数据、同样的版本号 | 两处版本号不一致 = 出现了第二份事实源（本批重构的硬约束） |

> 已知落差：课件「改一版」会回退默认配色主题（`style` 未随版本留痕）；无版本级删除与落盘回收。

### 1.4 知识图谱

| 步骤 | 预期现象 | 失败怎么判断 |
| --- | --- | --- |
| 打开 `/knowledge-graph`（先至少上传一份资料并等它「已完成」） | 画布画出知识点节点与关系线 | 画布空 = 该资料没提取出节点（stub 下只有正文前几行，见 `docs/api/stub-mode.md`） |
| 用「学科 / 章节」下拉过滤 | 画布只剩该范围内的节点；过滤条件出现在 URL（`?subject=` / `?chapter=`） | URL 不变 = 状态没上 URL（刷新会丢，属交互缺陷） |
| 点一个节点 | 右侧抽屉：内容 / 难度 / 重要度 / **来源引用** | 抽屉空 = 节点详情端点失败 |
| 在抽屉里把邻域切到 1 / 2 / 3 跳 | 画布切成以该点为中心的邻域子图，中心点用**强调色描边**（不是色块填充） | 中心点整块填色 = 违反扁平标准（填充会盖住黑字） |
| 清除过滤 / 退出邻域 | 回到全图 | 退不回去 = 视图状态没复位 |

> 已知落差：画布**无分页 / 无虚拟化**（节点很多时会卡）；**来源引用只到资料粒度**（不到段落）。

### 1.5 冲突审核

**重要前提**：队列里的三类冲突**不会自动齐**。
- **stub 模式**：stub 的比对恒返回「无矛盾」，队列自然为空 → 用附录 B 造种子数据后再做本节；
- **真实 Key**：定义冲突由检测自然产出；**结构冲突与常识存疑的检测逻辑尚未实现**（ADR-0006），
  这两类的**形态与动作**只能在种子数据下验收，不能拿「队列里没有」当故障。

| 步骤 | 预期现象 | 失败怎么判断 |
| --- | --- | --- |
| 打开 `/conflicts` | 按**类别**分区的队列，每区显示「N 条待审 · 共 M 条」 | 已裁决的冲突从列表里消失 = 违反「终态可复核」（应保留在列表里显示终态） |
| 看一条定义冲突卡片 | 新旧知识**对照**（左右两栏）+ 差异说明 + 三个按钮（接受新 / 保留旧 / 并存） | 只给一个按钮 = 类别动作集合收窄失效 |
| 看一条结构冲突卡片 | 除对照外还有「**图谱现状 vs 三种裁决终态**」的小图（三种终态各一张，新知用强调色描边） | 没有小图 = `structure_preview` 丢了（`docs/api/conflicts.md` 把它定为验收项） |
| 按下「接受新」 | 弹出/提示「已记下裁决：已接受」；卡片变成已裁决态；**图谱页**里旧节点位置换成了新知，关系边还在 | 图谱没变 = 裁决只写了状态没动图 |
| 再对同一条冲突按任意按钮 | 明确拒绝：`409`「这条冲突已经裁决过」 | 允许重复裁决 = 幂等边界破了 |
| 看一条常识存疑卡片 | **红旗标记 + 原文 + 两选一**（照常入库 / 拒绝）+ **编辑修正后入库**的编辑框 | 出现「并存」按钮 = 把两选一错做成三选一 |
| 在编辑框改对内容后点「编辑修正后入库」 | 落库的是**修正后的内容**（图谱节点里是改对的说法），原文留在冲突记录里 | 落库的还是原文 = 编辑修正没生效 |

> 已知落差：冲突**详情路由**（`/conflicts/:conflictId`）仍是占位；队列**不分页**。

### 1.6 题库

| 步骤 | 预期现象 | 失败怎么判断 |
| --- | --- | --- |
| 先在生成物区「一键生成试卷」，再打开 `/question-bank` | 列表出现刚生成的题目（按入库时间倒序） | 列表空 = 试卷没入题库（看生成响应的 `bank_saved`） |
| 用「考查知识点」下拉筛选 | 列表只剩该知识点的题；下拉里的知识点清单**不随筛选收窄** | 筛完就再也切不回别的知识点 = 筛选项被误做成随筛选变化 |
| 点一条题目 | 详情：题型 / 题干 / 答案 / 来源（自编 / 上传 / 网络）/ 考查知识点（主考 / 涉及） | 详情没有答案 = 契约缺字段 |
| 看「考查知识点」标注 | **只有当题干的知识点能对上图谱节点标题时才有标注**（stub 出题与你的资料往往对不上，属数据现象） | 一个标注都没有且你的资料里确实有对应知识点 = 匹配逻辑退化 |

> 已知落差：题目详情**不展示解析**（`questions` 表缺 `analysis` 字段，补列需同时改幂等补列）。

### 1.7 设置

| 步骤 | 预期现象 | 失败怎么判断 |
| --- | --- | --- |
| 打开 `/settings` | 四张卡：供应商目录 / 任务级模型 / 能力实现 / 自定义 OpenAI 兼容服务；每项都标「设置页」或「引导默认」 | 缺来源标记 = 教师分不清「我改过没有」 |
| 在「供应商目录」选一家并粘贴 Key，保存 | 提示保存成功；供应商标为已就绪；**输入框立刻变成掩码**（`••••尾4位`） | 明文回显在任何位置 = 违反「Key 回读只见掩码」 |
| 刷新页面 | 仍是刚配的供应商，Key 仍只显示掩码 | 掉回 stub = 设置没落库 |
| 改「任务级模型」（意图分析 / 生成 / 冲突比对） | 每档都能看到「选择的值」与「**实际用的是什么**」 | 只有「选择的值」没有「实际生效值」= 少了解析回落后的可见值 |
| 切「检索策略」为纯向量，保存，再去 `POST /api/v1/knowledge/retrieve`（或图谱/备课走一轮） | 当场生效，**不需要重启**；`strategy` 字段变成 `vector` | 需要重启才变 = 写穿失效（票 13 的核心验收点） |
| 切「PDF 解析策略」「语音转写」「网络搜索」并保存 | 各自就绪状态随之变化（缺 Key 时显示原因，不是崩溃） | 直接 500 崩页面 = 就绪探测没兜住 |
| 把某项改回空字符串保存 | 该项回落「引导默认」（`.env` / 代码默认） | 清不掉 = 清空语义没实现 |
| 用「自定义 OpenAI 兼容服务」填 base_url + 模型 ID + Key | 保存成功，且模型 ID 不受供应商目录限制 | 报「未知模型」= 自定义档没放行 |

---

## 2. 真实云端 Key 下的联通性

### 2.1 先把能力配起来

两种方式（**设置页优先于 `.env`**，见 `docs/api/stub-mode.md`「配置优先级」）：

- **设置页**（推荐，改完即时生效）：供应商目录选一家 → 粘贴 Key → 保存；再按需配
  「向量化 / 网络搜索 / PDF 解析 / 录音转写」。
- **`.env`**（引导默认）：`cp backend/.env.example backend/.env` 后填 Key，重启后端。

| 能力 | 变量 / 设置项 | 去哪拿 | 配置后的预期 |
| --- | --- | --- | --- |
| 对话 + 多模态 + 向量化 + 转写（阿里云百炼） | `DASHSCOPE_API_KEY`，供应商选 dashscope | 阿里云百炼控制台 | `llm_provider=dashscope`；图片 / 视频能真实识别；录音转写可用 |
| 对话（备选） | `DEEPSEEK_API_KEY`，供应商选 deepseek | DeepSeek 开放平台 | `llm_provider=deepseek`；**该家不支持图片 / 视频理解**，视觉调用仍会报错（预期行为） |
| 向量化（备选） | `SILICONFLOW_API_KEY`，`EMBEDDING_PROVIDER=siliconflow` | 硅基流动控制台 | 向量维度变为该模型维度（**换供应商后要删 `backend/data/vectors.db` 重建**，否则维度冲突） |
| PDF 解析（云端） | `MINERU_TOKEN`，`PDF_STRATEGY=mineru` 或 `mineru_then_pypdf` | mineru.net | 扫描件 PDF 也能解析出 Markdown；失败时自动退 pypdf（`mineru_then_pypdf` 档） |
| 网络搜索 | `BOCHA_API_KEY`，`SEARCH_PROVIDER=bocha` | 博查 | `POST /api/v1/knowledge/web-search` 返回真实网页结果（**不再是「（stub 网络搜索）」占位**） |

> **换 embedding 供应商后必须删 `backend/data/vectors.db`**：库里的向量维度是旧的，混用会报维度错误。
> 这是既定行为，不是缺陷（已在 `MEMORY`/README 里记过）。

### 2.2 一条命令验证四类服务（对话 / 向量化 / 搜索 / PDF）

```bash
cd backend
uv run python scripts/verify_services.py
```

**预期现象**：打印四段，每段都写清用的是哪个实现：

```text
=== 1. chat（LLM_PROVIDER=dashscope → OpenAICompatProvider）===
<一句中文回答>
=== 2. embed（OpenAICompatEmbedder）===
向量数=2, 维度=1024
=== 3. search（BochaSearch）===
结果数=5
- <真实网页标题> | <https://...>
=== 4. parse（PDF_STRATEGY=mineru_then_pypdf）===
<Markdown 正文>
```

**失败怎么判断**（按报错对号入座）：

| 现象 | 含义 | 处置 |
| --- | --- | --- |
| `XXX_API_KEY 未配置` | 工厂选了真实实现但 Key 为空（**不静默回落 stub**，有意为之） | 补 Key 或把该能力切回 stub |
| `401 / 403` | Key 错、过期、或没有该模型权限 | 换 Key / 换模型档位 |
| `404 model not found` | 模型 ID 不在该家目录里（或自定义服务填错） | 设置页选目录内的模型，或改用「自定义 OpenAI 兼容服务」 |
| `连接超时 / 无法解析主机` | 网络或 base_url 不对 | 检查 `base_url`、代理、防火墙 |
| `向量维度冲突` | 换过 embedding 供应商但没重建向量库 | 删 `backend/data/vectors.db` 后重跑 |
| 第 4 段跳过 | 仓库根目录没有 `test.pdf` | 放一份 PDF 到 `backend/test.pdf`（或直接在界面里上传验证） |

### 2.3 真实 Key 下值得单独看的四件事（stub 下看不到）

1. **澄清回复 + 跳过追问**（`spec.md` 用户故事 4/5）：先说「备课」→ 应追问；把粒度切「精细」→ 追问更细；
   说「开始生成」→ 直接出生成物。**判据**：追问形态与生成形态互斥，`clarifying` 字段与界面一致。
2. **定义冲突真的会被检测出来**：上传两份对同一知识点说法矛盾的资料 →
   `/conflicts` 出现「定义冲突」，裁决前图谱里**看不到**新知，裁决「接受新」后旧节点的边还在。
3. **真实的图谱 / 视觉提取**：`/knowledge-graph` 的节点标题来自你的资料正文（不再是
   「[stub 演示提取]」/「[stub 视觉提取]」占位）；图片 / 视频帧的解读反映画面内容。
4. **网络搜索**：`POST /api/v1/knowledge/web-search` 的结果是真实网页（无「（stub 网络搜索）」标记）。

---

## 3. 人眼判断的视觉项

### 3.1 先让机器把能扫的扫完

```bash
cd frontend
npm run check:classes   # 禁用 class 清单（风格文档第 6 节，10 条规则）——零违规才算过
npm run lint            # 上面 + oxlint
npm run build           # 上面 + tsc -b + vite build
```

**预期现象**：`[check:classes] 禁用 class 扫描通过：104 个文件，10 条规则零违规。`；构建成功。

### 3.2 机器扫不到、只能人眼看的（逐项打勾）

打开真浏览器，**逐区**（含空状态、加载中、失败态）过一遍：

- [ ] **零阴影**：卡片、抽屉、弹层都没有浮起感（`shadow-*` 机器已扫，这里看是否有 `style` 内联阴影 / 图片自带阴影）
- [ ] **零圆角**：按钮、输入框、卡片、弹层四角都是直角（含 Radix 弹层的边缘）
- [ ] **无灰底**：页面与容器只有黑/白/强调色三色，没有灰色填充块；**禁用态**是「边框 2px → 1px + 文字 `text-black/40`」
- [ ] **强调色只出现在该出现的地方**（当前项标记、关键动作按钮底、图谱关系线、错误与危险提示），且**强调色上只有黑字**
- [ ] **悬停是黑白反色**：把鼠标依次移到导航项、侧栏列表条目、按钮、下拉条目、卡片上——整块反色，**不位移、不缩放、不加阴影**；
      唯一例外是文本输入框（悬停为**边线加粗 2px → 4px**，不是实心黑块）
- [ ] **四态齐备**：默认 / 悬停 / 聚焦（Tab 键聚焦，可见且**不是**浏览器默认蓝圈）/ 禁用（边框变细 + 文字变淡）
- [ ] **动效**：只看到颜色变化，时长 ≤ 200ms；页面里没有循环动画（加载指示器的 `animate-spin` 除外）
- [ ] **密度双轨**：数据区（会话列表 / 资料列表 / 版本时间线 / 题目列表）紧凑；空状态 / 设置 / 引导页留白大、字号高一档
- [ ] **字体**：中文 Noto Sans SC、数字与英文 Space Grotesk；无外链字体（断网后字形不变）
- [ ] **无 emoji 装饰**，图标线宽一致、黑白线性
- [ ] **mermaid 扁平主题**（知识图谱区与结构冲突图示）：
      白底、黑框**直角**节点、直角折线；四种关系用「黑实线 / 黑粗实线 / 黑虚线 / **强调色虚线**」区分，
      没有 mermaid 默认的彩色分类色板与阴影；选中节点是**强调色描边**而不是填充
- [ ] **空 / 加载中 / 失败三态**都不退回默认样式（错误态用强调色 + 明确文案，不是灰块骨架屏）
- [ ] **键盘可达**：Tab 能走到主要控件，Esc 能关弹层 / 抽屉 / 下拉，对话框里 Tab 不跑出框（焦点陷阱）

任一项不过 → 按 `docs/style/minimalist-flat.md` 第 7 节定位到具体条目，改完重跑 3.1 再回来看。

---

## 附录 A. stub 模式全链路冒烟（可复现命令）

**用途**：机器能跑，但需要你本机执行并肉眼核对输出（不是点选判断）。
**前提**：不配任何 Key；用一个空闲端口（下面用 8000）；用**临时库与临时落盘目录**，别污染开发数据。

```powershell
# 终端 1：隔离跑一个 stub 后端
cd backend
$env:DATABASE_URL = "sqlite:///$env:TEMP/smoke/smoke.db"
$env:VECTORS_DB_PATH = "$env:TEMP/smoke/vectors.db"
$env:UPLOAD_DIR = "$env:TEMP/smoke/uploads"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# 终端 2：走一遍主链路（$base 固定，下面命令按顺序粘）
$base = 'http://127.0.0.1:8000'

# 1) 模式确认：预期 status=ok 且 llm_provider=stub
Invoke-RestMethod "$base/health"

# 2) 上传资料（PDF / 图片 / 视频各来一份；用 curl.exe，PowerShell 的 -Form 会按 RFC 2047 编码文件名）
curl.exe -s -X POST -F "file=@C:\path\to\tcp-handout.pdf" "$base/api/v1/documents/upload"   # 预期 status=处理中
curl.exe -s -X POST -F "file=@C:\path\to\whiteboard.png"  "$base/api/v1/documents/upload"
curl.exe -s -X POST -F "file=@C:\path\to\clip.avi"        "$base/api/v1/documents/upload"

# 3) 状态跟进：把上一步的 id 填进来，预期 处理中 → 已完成，chunk_count≥1
$doc = '<上传返回的 id>'
Invoke-RestMethod "$base/api/v1/documents/$doc"
#   图片 / 视频的分块应带「[stub 视觉提取]」（视频另有「[帧 N]」）——这是票 15 的验收点

# 4) 建会话（把 PDF 的 id 勾成参考资料）
$session = Invoke-RestMethod "$base/api/v1/sessions" -Method Post -ContentType 'application/json' `
  -Body (@{ title='TCP 三次握手（大二）'; granularity='标准'; reference_doc_ids=@($doc) } | ConvertTo-Json -Depth 6)
$session.id

# 5) 一轮备课（stub 下第一轮就是生成回复：意图固定且要素齐全）
$turn = Invoke-RestMethod "$base/api/v1/chat" -Method Post -ContentType 'application/json' `
  -Body (@{ session_id=$session.id; messages=@(@{ role='user'; content='给大二讲 TCP 三次握手，45 分钟' }) } | ConvertTo-Json -Depth 6)
$turn.clarifying      # 预期 False
$turn.artifacts.references   # 预期含你上传的文件名（溯源）

# 6) 生成物版本：列表 → 详情 → 下载
$versions = Invoke-RestMethod "$base/api/v1/sessions/$($session.id)/artifacts"
$versions.groups | ForEach-Object { "$($_.artifact_type) 共 $($_.versions.Count) 版" }   # 预期 课件/教案/提纲
$v = ($versions.groups | Where-Object { $_.artifact_type -eq '课件' }).versions[-1]
curl.exe -s -o "$env:TEMP\smoke\v.pptx" "$base/api/v1/artifacts/$($v.id)/download"   # 预期文件非空

# 7) 改一版：以历史版本为基线（预期版本号变大、旧版本仍在列表里）
$detail = Invoke-RestMethod "$base/api/v1/artifacts/$($v.id)"
# 提纲用 /revise/outline；课件用 /revise（见 /docs 的请求示例）
```

**预期汇总**：一条链路「上传 → 处理中 → 已完成 → 建会话 → 生成回复 → 版本列表 → 详情 → 下载 →
以基线改一版」全绿；图片 / 视频也走到「已完成」。**冲突审核**在 stub 下需要种子数据，见附录 B。

---

## 附录 B. 冲突三类别的人工验证（种子数据）

**为什么需要**：结构冲突与常识存疑的**检测逻辑尚未实现**（ADR-0006），而 stub 的比对恒返回「无矛盾」，
所以这两类的**形态与动作**只能由种子数据造出来给眼睛看。

在附录 A 那个临时库上种三条待审冲突（定义 / 结构 / 常识存疑各一条），然后刷新 `/conflicts`：

```powershell
# 与后端同一个库（同一个 $env:DATABASE_URL）
cd backend
$env:PYTHONPATH = '.'   # 脚本放在临时目录里，因此显式把 backend/ 加进导入路径
@'
from app.db import SessionLocal, init_db
from app.db.models import Conflict, KnowledgeNode, KnowledgeEdge

init_db()
db = SessionLocal()
old = KnowledgeNode(user_id="default", title="TCP 三次握手(旧)", content="旧描述：两次握手即可")
db.add(old); db.commit(); db.refresh(old)
up = KnowledgeNode(user_id="default", title="传输层协议(旧)", content="上层知识")
down = KnowledgeNode(user_id="default", title="报文段格式(旧)", content="下游知识")
db.add_all([up, down]); db.commit(); db.refresh(up); db.refresh(down)
db.add(KnowledgeEdge(user_id="default", from_node=up.id, to_node=old.id, relation_type="前置依赖"))
db.add(KnowledgeEdge(user_id="default", from_node=old.id, to_node=down.id, relation_type="父子包含"))
for category, new_knowledge, existing in [
    ("定义冲突", {"title": "TCP 三次握手(新)", "content": "新描述：必须三次握手"},
     {"id": old.id, "title": old.title, "content": old.content}),
    ("结构冲突", {"title": "TCP 连接建立(新)", "content": "新知识点",
                "relations": [{"from_title": "TCP 连接建立(新)", "to_title": down.title, "relation": "推导关系"}]},
     {"id": old.id, "title": old.title, "content": old.content}),
    ("常识存疑", {"title": "TCP 是 UDP 的别名", "content": "可疑常识"}, None),
]:
    db.add(Conflict(user_id="default", category=category, new_knowledge=new_knowledge,
                    existing_knowledge=existing, diff_description="人工验收种子", status="待审"))
db.commit()
print("seeded:", [row.category for row in db.query(Conflict).all()])
db.close()
'@ | Set-Content -Path "$env:TEMP\seed-conflicts.py" -Encoding utf8
uv run python "$env:TEMP\seed-conflicts.py"
Remove-Item Env:PYTHONPATH
```

**预期现象**：打印 `seeded: ['定义冲突', '结构冲突', '常识存疑']`；刷新 `/conflicts` 后三个类别分区
各有一条待审（结构冲突带「图谱现状 vs 三种裁决终态」小图）。之后按 1.5 节的表格逐项裁决并观察图谱变化。

> 只想验证**动作契约**而不看界面时，`uv run pytest tests/test_conflict_categories.py -q` 已经把
> 三类别、差异化动作、终态与图谱变迁都钉住了（包括 `409` 幂等边界与 `422` 类别不符）。
