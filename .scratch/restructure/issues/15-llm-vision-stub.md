# 15: 视觉提取的 stub（补能力注册缺口）

**What to build:** 补上 ADR-0003「接口 + 工厂 + 必有 stub」的一处缺口：对话能力的 stub 只实现了文本对话，**视觉提取没有 stub**，导致无任何云端 Key 时上传图片 / 视频必然解析失败——多模态这条主路径在 stub 模式下走不通。补一个带标记的 stub 视觉提取，让「无 Key 全链路可跑」这条底线在图片 / 视频上也成立；有 Key 的真实 provider 行为不变。

**Blocked by:** 02 能力注册统一

**Status:** ready-for-agent

- [x] `StubProvider` 实现对话接口里的视觉提取，返回带「stub 视觉提取」标记的确定性结果，不再抛 `NotImplementedError`
- [x] 无任何云端 Key 时上传图片与视频，解析状态能走到终态「已完成」（不再必然「失败」）
- [x] 有 Key 的真实 provider 路径行为不变（既有契约测试保持绿）
- [x] 经 HTTP 缝测试覆盖「stub 模式下上传图片 → 状态到终态」，且既有 stub 全链路测试保持绿

## 由来（协调者据交付记录取证建票）

票 09（知识库工作台）的交付记录报告：图片 / 视频在无 Key 的 stub 模式必然落「失败」，因为
`backend/app/core/llm/base.py` 的视觉能力没有 stub 实现（`StubProvider` 只实现了 chat，
视觉方法抛 `NotImplementedError`）。

这与两处既有决策冲突：

- `docs/adr/0003-capability-registry.md`：每项能力都是「接口 + 按配置选择的工厂 + 必有 stub」；
- `backend/AGENTS.md` 分层铁律：外部能力「新实现必须同时提供 stub」；
- `docs/api/stub-mode.md`：无任何云端 Key 时全链路必须可跑。

并且会直接卡住票 14 的多模态端到端冒烟（「上传 → 备课对话 → 生成物 → 下载」这条链路在图片 / 视频上演示不出来）。

**范围边界**：本票只补 stub，不改真实 provider 的视觉实现，不改上传接口语义，不动知识库区前端。

## 交付记录

**分支**：`JulianZBY/issue-15-llm-vision-stub`（本工作树当前分支；未 push、未开 PR、未 merge/rebase）
**主提交**：`aef73d9` · `fix(15): 补视觉提取 stub（stub 模式多模态链路可跑）`
**收尾提交**：本节的勾选与记录（`docs(15): 勾选验收项 + 交付记录`）。

### 一、跑过的命令与结果

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv sync` | 成功（本工作树原先无 `.venv`；无 setup 钩子） |
| `uv run pytest -q --ignore=tests/test_vision_stub.py` | 通过：**238 passed**（本票改动前的基线） |
| `uv run pytest -q` | 通过：**242 passed**（= 238 + 本票新增 4 条） |
| `uv run pytest tests/test_vision_stub.py -q` | 通过：**4 passed**（本票新增的缝测试） |
| `uv run pytest tests/test_openai_compat_contract.py -v` | 通过：**10 passed**（真实 provider 契约，含视觉两例） |
| `uv run ruff check .` | 通过：`All checks passed!` |
| 真服务实测（uvicorn 8123，无任何 Key） | 见第三节：图片与视频都 `处理中 → 已完成` |
| 落盘隔离核对 | `backend/data` 文件数 90 → 90：跑本票测试不新增任何落盘 |
| `git status --short` | 收尾时干净（仅提交内的文件，无残留） |

### 二、验收项 1：stub 视觉提取（确定 + 带标记）

`backend/app/core/llm/providers/stub.py` 追加
（**只在文件末尾追加**：一个模块级常量 + `StubProvider` 的一个方法，未重排任何既有 import 或代码块）：

```python
_STUB_VISION_MARK = "[stub 视觉提取]"
_STUB_VISION_TEXT = (
    f"{_STUB_VISION_MARK}（占位解读，不是真实识别结果）本次运行没有可用的云端多模态能力，"
    "图片与视频帧的解读由 stub 返回固定内容，不反映画面实际内容。"
    "画面要点：教学示意图（占位）；可提取知识点：接入云端多模态能力后由真实识别给出。"
)

class StubProvider(LLMProvider):
    ...
    async def vision(self, image_path: str, prompt: str) -> str:
        return _STUB_VISION_TEXT
```

- **确定性**：模块级常量、不含随机数/时间/网络；同一个输入连调两次字符串完全相同（测试断言 `first == second`）。
- **标记与措辞**：首字符即 `[stub 视觉提取]`，照抄 stub 文本对话的标记风格（方括号 + `stub` 前缀，`[stub] …` / `[stub 演示提取]`）；
  正文接着写明「占位解读，不是真实识别结果」，避免教师误读。用词按 `CONTEXT.md` 第 8 节措辞纪律：只说 **stub**，没有写「演示模式」「离线模式」。
- **入参不使用**：stub 无云端多模态可读图，也不需要 prompt（文档字符串里写明这是接口签名保留，输出与入参无关，便于断言）。
- 未改 `base.py`：`vision` 的默认 `NotImplementedError` 保留——真实 provider 缺多模态模型时仍然照旧抛错（见验收项 3）。

### 三、验收项 2：无 Key 时图片 / 视频走到终态「已完成」

**证据 A（HTTP 缝，自动）**：见验收项 4 的用例表；图片与视频两条路径各自覆盖（视频解析路径与图片不同：OpenCV 抽帧后逐帧走同一视觉能力）。

**证据 B（真服务实测，uvicorn 8123，临时库 / 临时落盘，无任何云端 Key）**：

```powershell
# 图片
POST /api/v1/documents/upload  (board.png)  -> status=处理中  file_type=png
GET  /api/v1/documents/{id}                 -> status=已完成  chunk_count=1  parsed_at=2026-09-24 19:19:50
  first chunk: [stub 视觉提取]（占位解读，不是真实识别结果）本次运行没有可用的云端多模态能力，图片与视频帧的解读由 stub 返…
# 视频
POST /api/v1/documents/upload  (clip.avi, MJPG 8 帧) -> status=处理中  file_type=avi
GET  /api/v1/documents/{id}                          -> status=已完成  chunk_count=1  parsed_at=2026-09-24 19:19:50
  first chunk: [帧 1] [stub 视觉提取]（占位解读，不是真实识别结果）本次运行没有可用的云端多模态能力，图片与视频帧的解读由…
# 模式确认
GET  /health  -> {"status":"ok","app":"EduMind","llm_provider":"stub"}
```

上传用 `curl.exe`（不用 PowerShell `Invoke-RestMethod -Form`：它会按 RFC 2047 编码文件名，导致 `file_type` 为空）。
状态口径用 `CONTEXT.md` 第 4 节的词：**处理中** → **已完成**（本票不涉及「有冲突」，stub 视觉文本逐份资料同名同文，重名节点走既有「重复不入图」路径）。

### 四、验收项 3：真实 provider 路径行为不变

- **代码证明**：`git diff --stat` 只有 `backend/app/core/llm/providers/stub.py`（+15 行）；
  `openai_compat.py`、`factory.py`、`dialects.py`、上传接口、解析器调用点全部一行未改。
- **契约测试（既有，保持绿）**：`uv run pytest tests/test_openai_compat_contract.py -v` → **10 passed**，其中视觉两例：
  - `test_dashscope_dialect_sends_multimodal_payload`：真实多模态仍按 `vision_model=qwen-vl-max` 打 parts 数组；
  - `test_deepseek_dialect_sends_plain_chat_payload`：该方言无多模态模型 → `vision` **仍然**抛 `NotImplementedError`（stub 之外的 provider 行为未变）。

### 五、验收项 4：测试（新增缝用例名与结果）

`cd backend && uv run pytest tests/test_vision_stub.py -q` → **4 passed**（`uv run pytest -q` → 242 passed）

| 用例名 | 缝 | 断言的是**可观测结果** |
| --- | --- | --- |
| `test_stub_provider_vision_returns_marked_deterministic_text` | 能力缝（stub 实现） | 首行即 `[stub 视觉提取]`、两次调用同文（确定性）、正文含「不是真实识别」 |
| `test_vision_is_reachable_through_the_selected_provider_in_stub_mode` | 能力缝（工厂选择） | 无 Key 时 `get_llm()` 选中的 provider 就能做视觉提取（ADR-0003 的「接口 + 工厂 + 必有 stub」） |
| `test_image_upload_reaches_completed_in_stub_mode` | **HTTP 缝** | 上传真实 PNG：`处理中` → 终态 **`已完成`**、`parsed_at` 有值、分块非空且带 `[stub 视觉提取]` |
| `test_video_upload_reaches_completed_in_stub_mode` | **HTTP 缝** | 上传真实 AVI（MJPG，测试内用 OpenCV 现场生成）：`处理中` → **`已完成`**，分块内容含 `[帧 ` 与 `[stub 视觉提取]` |

既有 stub 全链路测试保持绿：`tests/test_documents_workbench.py`（8 条 HTTP 缝，含录音走 stub 转写 → `已完成`）、
`tests/test_documents.py`、`tests/test_llm_stub.py`、`tests/test_audio.py` 一起跑 → **27 passed**。
落盘隔离沿用 `tests/conftest.py`（`DATABASE_URL` / `VECTORS_DB_PATH` / `UPLOAD_DIR`），实测 `backend/data` 文件数不变。

### 六、新增 / 改动文件清单

- 新增 `backend/tests/test_vision_stub.py`（4 条缝测试：2 条能力缝 + 2 条 HTTP 缝，自造真实 PNG/AVI，不依赖网络与 Key）
- 改动 `backend/app/core/llm/providers/stub.py`（追加 `_STUB_VISION_MARK` / `_STUB_VISION_TEXT` 与 `StubProvider.vision`，+15 行）

**未改**（并行协作纪律 + 本票范围边界）：`core/llm/base.py`、`core/llm/providers/openai_compat.py`、`core/llm/factory.py`、`core/dialects.py`、
`knowledge/parsers/**`（图片 / 视频解析器调用点无需改动）、`app/api/**`、`db/models.py`、`docs/**`、`CONTEXT.md`、`frontend/**`、
以及 `.scratch/**` 里非本票的文件。改动一律追加，未重排既有 import 或代码块。

### 七、遗留问题

1. **stub 视觉文本与画面无关**：固定一段占位解读，图片与视频帧内容相同（stub 模式本来「内容质量不作承诺」；
   图片没有可回显的文本层，做不到像图谱 stub 那样「回显正文前几行」）。要真实识别须配云端 Key，属 `ready-for-human`。
   影响面：stub 下同一批资料会得到同名同文的提取节点，重复上传走既有「重名不入图」路径，不会误报「有冲突」。
2. **视频帧数上限是既有行为**：`VideoParser` 取 `n = min(4, 总帧数)` 帧，stub 下这 4 帧同文；超长视频的覆盖度问题不在本票范围。
3. **网络搜索仍无 stub**（`docs/api/stub-mode.md` 有意为之），因此票 14 的 stub 冒烟里搜索这条仍须排除——本票只补上图片 / 视频这两条，不改变搜索的口径。
4. **`backend/data/output` 是既有共享落盘路径**（其它票已记录）：本票测试不写它（实测 90 → 90）；本票没有新增隔离需求。
5. **没有真浏览器验证**：本票只碰后端，浏览器端「上传图片 → 看到已完成」留给票 14 的 Playwright 冒烟。

## 协调者复核

（待交付后填写）
