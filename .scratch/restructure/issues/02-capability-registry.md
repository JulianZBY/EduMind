# 02: 能力注册统一

**What to build:** 换任何云端能力只改配置不改代码。对话与向量化收敛为单一 OpenAI 兼容 provider——填 base_url / 模型名 / Key 即可在 dashscope、deepseek、硅基流动之间切换；向量化从对话 provider 拆成独立接口与工厂；语音转写与网络搜索补齐「接口 + 必有 stub」（搜索此前只有写死的客户端、无兜底）；PDF 解析提供 mineru / pypdf / mineru 失败退 pypdf 三种可选策略，替换写死在解析类里的兜底。对教师行为不变；无 Key 的 stub 模式仍是全链路底线。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 五项能力（对话 / 向量化 / 语音转写 / PDF 解析 / 网络搜索）都是接口 + 按配置选择的工厂，新增实现无需改动调用方
- [ ] OpenAI 兼容 provider 经 MockTransport 契约测试覆盖三家方言各一例
- [ ] 向量化是独立接口，调用方不再依赖对话 provider
- [ ] PDF 三策略可经配置切换，失败兜底行为有测试
- [ ] stub 模式全链路可跑（既有底线测试保持绿）
