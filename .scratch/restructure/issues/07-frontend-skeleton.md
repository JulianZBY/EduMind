# 07: 前端骨架

**What to build:** 新前端的骨头先立起来:六区(会话/知识库/产物/知识图谱/冲突审核/题库)+ 设置的导航路由(默认落在会话区)、Minimalist Flat 基线组件(Button/Input/Card/Tag/弹层/抽屉/Toast,交互原语用 Radix)、服务端状态与 UI 状态接线、从后端 OpenAPI schema 生成 TS 类型的管线、禁用类扫描脚本。各区为空壳但可导航、风格到位(ADR-0005)。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 七条路由可达,默认路由=会话区
- [ ] 基线组件逐项通过风格文档自检清单(零阴影/零渐变/零灰底/border-2 border-black/rounded-none/悬停黑白反色)
- [ ] TS 接口类型全部由 OpenAPI 生成,仓库无手抄接口类型
- [ ] 禁用类扫描脚本挂入 lint/build,能拦截违规 class
- [ ] 骨架采用工作台密度(风格文档密度双轨)
