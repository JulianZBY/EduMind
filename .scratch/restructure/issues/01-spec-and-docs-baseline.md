# 01: 规范与决策文档基线

**What to build:** 让仓库里每一条「必读指针」都能打开，并把已定决策固化成记录，使后面 13 张工单的验收标准都有出处。补出 ADR-0002~0005（后端唯一事实源 / 能力注册 / 冲突三类别 / 前端骨架与技术选型）、架构一页图、Minimalist Flat 风格硬标准（含禁用 class 清单与交付自检清单）、领域词汇表、agent 协作规范（issue tracker / triage labels / domain）；既有全部端点按接口纪律补 summary、描述、请求响应示例、错误码、tag。

同批解决两处正面冲突，不留静默偏差：① 现存词汇表的「当前版本」词条写死「历史文件仅落盘、不展示、不构成版本树」，与全版本留痕决策相反；② 规格里六区之一叫「产物」，词汇表术语是「生成物」。

**Blocked by:** None (can start immediately)

**Status:** done

- [x] AGENTS.md 与工单引用的每一份文档都能打开：ADR-0002~0005、架构一页图、风格文档、词汇表、agent 协作规范三份
- [x] 风格文档含禁用 class 清单与交付自检清单，前端工单可逐项核对
- [x] 词汇表的版本用语与全版本留痕一致，六区命名统一用「生成物」
- [x] 既有全部端点在 OpenAPI 中带 summary、描述、示例、错误码、tag
- [x] 文档进入版本控制（从本地排除名单移除 docs/ 与词汇表），过程稿 DESIGN/PLAN/proposal 维持本地不入库

## 交付记录

### 分支与提交

| 项 | 值 |
| --- | --- |
| 分支 | `JulianZBY/issue-01-spec-docs` |
| 基线 commit | `eadc76c`（分支起点） |
| 本票 commit | `f8d04b0` — `docs(01): 规范与决策文档基线 + 端点 OpenAPI 注解`（文档、注解与契约测试全部在此提交；本交付记录连同验收项勾选为其后的第二个提交） |
| 未做 | 未 push、未开 PR、未 merge / rebase |

### 新建文档清单（14 份，全部入库）

| 文件 | 内容 |
| --- | --- |
| `CONTEXT.md` | 根领域词汇表：六区 + 设置、备课会话、生成物与版本用语、知识库、图谱、冲突、题库、设置与 stub 措辞 |
| `docs/adr/0002-backend-source-of-truth.md` | 后端是会话与生成物的唯一事实源（全版本留痕 / 状态机收编 / 意图累积 / 不迁移旧数据） |
| `docs/adr/0003-capability-registry.md` | 外部能力统一注册：接口 + 工厂 + 必有 stub；七项能力清单；向量存储不抽象 |
| `docs/adr/0004-conflict-categories.md` | 冲突三类别与差异化动作（三选一 / 两选一 + 编辑修正后入库）；检测逻辑不在本轮 |
| `docs/adr/0005-frontend-foundation-and-stack.md` | 前端六区骨架与布局、技术选型、OpenAPI 生成类型、风格守门方式 |
| `docs/architecture.md` | 目标架构一页图（mermaid）+ 分层职责 + 六区表 + 两条主数据流 + 现状与目标落差 |
| `docs/style/minimalist-flat.md` | 视觉与交互硬标准、**禁用 class 清单（10 条正则）**、**交付自检清单**、mermaid 扁平主题配方 |
| `docs/agents/issue-tracker.md` | 工单目录约定与固定五节格式、七条工单纪律、交付记录要求 |
| `docs/agents/triage-labels.md` | 五个标签的含义 / 谁能标 / 迁移规则；`ready-for-agent` 的硬条件 |
| `docs/agents/domain.md` | 单上下文文档地图、CONTEXT.md 与 ADR 的维护规则、docs/api/ 的边界 |
| `docs/api/README.md` | 接口专题索引 + 通用约定（前缀与版本、错误体形状、错误码选择、单用户） |
| `docs/api/conflicts.md` | 为什么需要专题、裁决状态机、三选一/两选一动作矩阵、存量回填、前端读法 |
| `docs/api/artifacts.md` | 文件名从哪来、`inline` 用途、安全边界、版本与文件一一对应（票 07 生效） |
| `docs/api/stub-mode.md` | 各能力无 Key 时的行为差异、配置优先级、不静默回落的理由 |

`docs/api/` 的建立理由：确有 OpenAPI 表达不了的语义——裁决动作对图谱做了什么、每条冲突只能裁决一次为何是 409、
常识存疑为什么没有「并存」、生成物文件名不可反推语义、网络搜索为什么故意没有 stub。
这些写成端点镜像文档没有价值，写成专题才能回答「读接口读不懂」的问题。

### 改动清单

- 新增 `backend/app/api/openapi_examples.py`：响应示例与错误码文案的唯一出处（含 422 / 500 / 未配置 Key 的公用片段）。
- 端点注解（只加元数据）：`backend/app/main.py`（`openapi_tags` 六分组 + 应用描述 + 根端点）、
  `backend/app/api/health.py`、`backend/app/api/v1/{router,chat,conflicts,documents,exam,files,interactive,knowledge,revise}.py`。
  每个端点补 `summary` / 描述 / 请求或响应示例 / 错误码（含含义）/ `tags`；请求模型加 `json_schema_extra` 示例；
  查询与路径参数补 `description`。**路径、行为、响应模型字段均未改动。**
- 新增 `backend/tests/test_openapi_contract.py`：36 个用例（16 个端点的 two-axis 参数化 + 4 个全局断言）。
- 术语消解：`backend/app/api/v1/interactive.py` 模块说明「产物区」→「生成物区」；
  `frontend/AGENTS.md` 信息架构行「产物」→「生成物」。
- `.git/info/exclude`（本机配置，不入库）：移除 `/docs/` 与 `/CONTEXT.md` 两行；
  `/proposal.md`、`/DESIGN.md`、`/PLAN.md`、`paseo.json` 四行保持不动。

### 跑过的命令与结果

```powershell
cd backend
uv sync                     # 依赖就绪（全新工作树，.venv 不在版本控制内）
uv run pytest -q            # 基线 95 passed → 交付后 131 passed（新增 36 个契约用例），2 个第三方 DeprecationWarning
uv run ruff check .         # All checks passed!
```

端点注解可复现证明（16 个 operation，含 `/api/v1/**` 全部 15 条；`example=True` 即带请求或响应示例）：

```powershell
cd backend
uv run python -c "from app.main import app; ops=[(p,m.upper(),(o.get('tags') or ['-'])[0],'example' in str(o)) for p,i in app.openapi()['paths'].items() for m,o in i.items()]; print(f'{len(ops)} operations'); [print(f'{p:46s} {m:5s} {t:6s} example={e}') for p,m,t,e in sorted(ops)]"
```

```text
16 operations
/                                              GET   系统     example=True
/api/v1/chat                                   POST  备课会话   example=True
/api/v1/conflicts                              GET   冲突审核   example=True
/api/v1/conflicts/{conflict_id}/review         POST  冲突审核   example=True
/api/v1/documents                              GET   知识库    example=True
/api/v1/documents/upload                       POST  知识库    example=True
/api/v1/exam/generate                          POST  生成物    example=True
/api/v1/files/{filename}                       GET   生成物    example=True
/api/v1/interactive/generate                   POST  生成物    example=True
/api/v1/knowledge/graph                        GET   知识图谱   example=True
/api/v1/knowledge/search                       POST  知识库    example=True
/api/v1/knowledge/web-search                   POST  知识库    example=True
/api/v1/ping                                   GET   系统     example=True
/api/v1/revise                                 POST  生成物    example=True
/api/v1/revise/word                            POST  生成物    example=True
/health                                        GET   系统     example=True
```

契约测试本身也可作为证明（每个端点两条断言，全绿）：

```powershell
cd backend
uv run pytest tests/test_openapi_contract.py -q     # 36 passed
```

文档入库与过程稿边界：

```powershell
git check-ignore -v docs/architecture.md CONTEXT.md   # 无输出 → 已不再被本地排除
git ls-files docs CONTEXT.md                          # 列出全部 14 份文档
```

### 与约束的一处显式偏差（已披露，非静默）

`backend/app/api/v1/chat.py` 里一句**面向教师**的回复文案由「可在产物预览区打开」改为「可在生成物区打开」。
依据是本票第 3 条（六区命名一律用「生成物」）+「面向教师文案一律用词汇表术语」；该字符串无测试断言，
路径、行为、响应模型字段均未改动。除此以外只加元数据。

### 遗留问题

1. **ADR-0001 缺位**：`backend/app/config.py`、`backend/app/knowledge/conflict.py`、`backend/app/api/v1/conflicts.py`
   与 `spec.md` 都引用 ADR-0001（定义冲突的检测与三选一），该记录不在本工作树。本票只重建 0002~0005，
   未凭空重建 0001；ADR-0004 已声明「在其上扩展」，建议随票 11 补一份或正式并入 0004。
2. **「产物」仍残留在本票 ownership 之外的四处**（`README.md`、`frontend/src/App.tsx` 的标签页与文案、
   若干后端注释、`.scratch/restructure/spec.md` 的六区描述）。规范文档已统一为「生成物」；
   前端部分随票 04/06 重写清理，README 随票 14 收口。
3. **`backend/app/db/models.py` 的模块 docstring 指向 `DESIGN.md §3.3`**，而 DESIGN.md 按设计不入库 → 仓库内断链
   （不在本票 ownership，未改；票 05 动该文件时应顺手修正）。
4. **题库分组暂缺**：题库查询端点（票 12）尚不存在，因此 OpenAPI 暂无「题库」tag 分组。
   契约测试要求「声明的分组必须有端点使用」，故票 12 落地时必须同时补分组与端点。
5. **docs/api/artifacts.md 的版本语义随票 07 生效**（当前只有「每次生成都是新文件、不覆盖」是既成事实）；
   票 07 落地后需回校该文档与 `docs/architecture.md` 的落差节。
6. **GET 型系统端点的错误码是通用 500**（未捕获异常）：`/health`、`/api/v1/ping`、`/` 没有业务错误分支，
   契约测试要求「每个端点至少记录一个错误响应」，因此记录的是事实性的通用 500，而非新增的承诺。

## 协调者复核

**结论：通过。** 复核人 = 协调者（主代理），2026-09-24。复核方式 = 独立复验，不采信交付记录里的自报数字。

| 验收项 | 复验方式 | 结果 |
| --- | --- | --- |
| 必读指针全可打开 | `git ls-files` 确认 14 份文档入库（ADR-0002~0005 / architecture.md / minimalist-flat.md / agents×3 / api×4 / CONTEXT.md） | 通过 |
| 风格文档含禁用清单 + 自检清单 | 通读 `docs/style/minimalist-flat.md`：10 条禁用 class 正则 + 7 节交付自检清单 + mermaid 扁平主题配方 | 通过 |
| 词汇表用语与全版本留痕一致 | 通读 `CONTEXT.md`：新增「版本用语（硬约束）」节并点名禁用表述；「产物」列作禁用写法 | 通过 |
| 全端点 OpenAPI 注解 | 协调者独立执行 `app.openapi()`：paths 16 / operations 16 / 缺 summary、description 或 tags 的端点 = `[]` | 通过 |
| 文档入库、过程稿仍排除 | `.git/info/exclude` 只剩 `DESIGN.md` / `PLAN.md` / `proposal.md` / `paseo.json` 四条 | 通过 |
| 测试与静态检查 | 协调者亲跑 `uv run pytest -q` → **131 passed**；`uv run ruff check .` → 干净 | 通过 |

- **合并点**：`19071fd`（`merge(01)`）。合并后与分支树逐步一致（`git diff main <分支> --stat` 为空）。
- **越界披露（接受）**：`frontend/AGENTS.md` 六区那一行（「产物」→「生成物」）—— 属验收项 3 的必需修正，范围合理。
- **状态迁移**：`ready-for-agent` → `done`（由本轮复核产生）。
- **遗留去向（协调者登记，不当口头约定）**：① ADR-0001 缺位 → 随票 11 处理；② README / `frontend/src/App.tsx` 的「产物」残留 → 票 04/06 与票 14；③ `backend/app/db/models.py` 指向不入库 DESIGN.md 的断链 → 已写入票 05 派发约束；④ 题库 OpenAPI 分组 → 已写入票 12 派发约束；⑤ `docs/api/artifacts.md` 版本语义回校 → 已写入票 07 派发约束。
