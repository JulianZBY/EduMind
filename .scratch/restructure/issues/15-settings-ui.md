# 15: 设置界面

**What to build:** 像 pi/opencode 一样配置模型:供应商/模型目录+粘贴 API Key 即用;按任务(意图分析/生成/冲突比对)选模型档位,未设回落全局默认;添加自定义 OpenAI 兼容服务(base_url+模型 ID);ASR/PDF 解析/搜索能力切换也在本页。改动即时生效,Key 全程只见掩码。采用编辑密度。

**Blocked by:** 05 设置存储+设置 API; 07 前端骨架

**Status:** ready-for-agent

- [ ] 目录选择+填 Key 后无重启即生效(可当场验证 stub→真实切换)
- [ ] 任务级模型选择与回落全局默认的行为可见
- [ ] 自定义 OpenAI 兼容接入(base_url+模型 ID)可用
- [ ] Key 全程掩码,表单不回显明文
- [ ] 能力切换(ASR/PDF 策略/搜索)即时生效
