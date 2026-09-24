# 01: 能力注册统一

**What to build:** 任何云端能力(LLM 对话/嵌入/ASR/PDF 解析/网络搜索)都成为可配置替换的模块:抽象接口 + 实现 + 配置按名选择 + stub 兜底。LLM 对话与嵌入收敛为单一 OpenAI 兼容 provider——配置 base_url/模型名/Key 即可在 dashscope / deepseek / 硅基流动(三家同为 OpenAI 兼容方言)间切换;PDF 解析提供 mineru / pypdf / mineru 失败退 pypdf 三种可选策略(替换写死在类里的兜底);网络搜索补齐接口与 stub。对教师行为不变;对维护者,换实现只改配置不改代码(ADR-0003)。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 五项能力全部走「接口+工厂按配置选择」,新增实现无需改动调用方
- [ ] OpenAI 兼容 provider 经 MockTransport 契约测试覆盖三家方言各一例
- [ ] Embedder 独立接口,与对话 provider 解耦
- [ ] PDF 三策略可经配置切换,失败兜底行为有测试
- [ ] stub 模式全链路可跑(既有底线测试保持绿)
