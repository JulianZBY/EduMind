# 14: 端到端验收收口

**What to build:** 重构收口：stub 模式全链路冒烟（上传 → 备课对话 → 生成物 → 下载 → 冲突审核），风格自检清单全过、禁用类扫描零违规，主干任一时刻可跑，规格 36 条用户故事逐条核对；README、架构一页图、接口专题与现实一致。

**Blocked by:** 01–13 全部 + 15 视觉提取的 stub

**Status:** ready-for-agent

- [ ] stub 模式从文档上传到备课对话到生成物下载全流程走通，且**图片/视频上传在 stub 模式下不再必然失败**（依赖票 15）
- [ ] 风格自检清单逐项通过，禁用类扫描零违规
- [ ] 规格 36 条用户故事逐条可演示或可解释
- [ ] README、架构一页图、接口专题与现实一致
- [ ] 后端测试全绿，主干按 README 步骤可跑
- [ ] **测试套件不密封（2026-09-24 协调者实测发现，本票收口）**：测试结果受开发者 `backend/.env` 影响——main 工作树有 `.env`（`LLM_PROVIDER=dashscope` + 真实 Key）时，全量测试跑 13.5 分钟并在 `tests/test_artifact_versions.py` 出现 3 条假失败（断言的是 stub 固定产出）；把 `LLM_PROVIDER=stub` 后同样代码 **274 passed / 13 秒**。要求在 `tests/conftest.py` 用 `os.environ.setdefault` 钉住 stub 类配置（至少 `LLM_PROVIDER` / `EMBEDDING_PROVIDER`，按需含 `SEARCH_PROVIDER` / `PDF_STRATEGY`），使测试不依赖任何真实 Key 与网络；验收方式：**把 `backend/.env` 里的 provider 设为真实值（或直接拷一份 `.env`）后全量跑，仍必须全绿且耗时稳定**。
- [ ] **补齐既有操作的 `response_model`（票 04 报告的缺口，本票收口）**：票 04 指出 6/16 操作缺 `response_model`，导致前端生成类型是 `unknown`；新增端点已由各票自带，**历史缺口在此补齐**，补完重跑 `npm run gen:api` 并确认前端类型不再是 `unknown`。
