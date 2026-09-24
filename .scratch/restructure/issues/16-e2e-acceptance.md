# 16: 端到端验收

**What to build:** 重构收口:stub 模式全链路冒烟(上传→备课对话→生成物→下载→冲突审核)、风格自检清单全过、主干可跑验证、规格 36 条用户故事逐条核对;README、架构图、接口专题与现实一致。

**Blocked by:** 01–15 全部工单

**Status:** ready-for-agent

- [ ] stub 模式从文档上传到备课对话到生成物下载全流程走通
- [ ] 风格自检清单逐项通过,禁用类扫描零违规
- [ ] 规格(`.scratch/restructure/spec.md`)36 条用户故事逐条可演示或可解释
- [ ] README、docs/architecture、接口专题与现实一致
- [ ] 后端测试全绿,主干 `git pull` 后按 README 步骤可跑
