# EduMind 前端规范

React 19 + Vite + TypeScript;Tailwind CSS + Radix 无头原语 + 自建扁平组件库;TanStack Query(服务端状态)+ zustand(UI 状态)+ react-router。不用组件库(ADR-0005)。

## 命令

```bash
npm install
npm run dev      # 开发
npm run build    # tsc -b && vite build
npm run lint     # oxlint
```

## 验收硬标准

`docs/style/minimalist-flat.md` — 零阴影/零渐变/零灰底/`border-2 border-black`/`rounded-none`/悬停黑白反色;禁用 class 清单与交付自检清单都在该文档,交付前逐项过。

## 结构约定

- 自建组件住 `src/components/`(扁平皮肤,交互原语用 Radix,无障碍由 Radix 承担)。
- API 类型从后端 OpenAPI schema 生成,**禁止手抄接口类型**。
- 服务端数据一律 TanStack Query;跨组件 UI 状态才用 zustand。
- 信息架构:六区(会话/知识库/产物/图谱/冲突/题库)+ 设置,默认路由 = 会话;布局见 `docs/architecture.md`。
