# 15: 视觉提取的 stub（补能力注册缺口）

**What to build:** 补上 ADR-0003「接口 + 工厂 + 必有 stub」的一处缺口：对话能力的 stub 只实现了文本对话，**视觉提取没有 stub**，导致无任何云端 Key 时上传图片 / 视频必然解析失败——多模态这条主路径在 stub 模式下走不通。补一个带标记的 stub 视觉提取，让「无 Key 全链路可跑」这条底线在图片 / 视频上也成立；有 Key 的真实 provider 行为不变。

**Blocked by:** 02 能力注册统一

**Status:** ready-for-agent

- [ ] `StubProvider` 实现对话接口里的视觉提取，返回带「stub 视觉提取」标记的确定性结果，不再抛 `NotImplementedError`
- [ ] 无任何云端 Key 时上传图片与视频，解析状态能走到终态「已完成」（不再必然「失败」）
- [ ] 有 Key 的真实 provider 路径行为不变（既有契约测试保持绿）
- [ ] 经 HTTP 缝测试覆盖「stub 模式下上传图片 → 状态到终态」，且既有 stub 全链路测试保持绿

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

## 协调者复核

（待交付后填写）
