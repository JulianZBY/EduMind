# EduMind 前端规范

React 19 + Vite + TypeScript;Tailwind CSS + Radix 无头原语 + 自建扁平组件库;TanStack Query(服务端状态)+ zustand(UI 状态)+ react-router。不用组件库(ADR-0005)。

## 命令

```bash
npm install
npm run dev          # 开发
npm run lint         # 禁用 class 扫描(风格文档第 6 节)+ oxlint
npm run build        # 禁用 class 扫描 + tsc -b + vite build
npm run check:routes # 七条路由可达 + 默认路由 = 备课会话(无浏览器)
npm run gen:api      # 从后端 OpenAPI 刷新快照并生成 TS 类型(前置:cd backend && uv sync)
```

## 验收硬标准

`docs/style/minimalist-flat.md` — 零阴影/零渐变/零灰底/`border-2 border-black`/`rounded-none`/悬停黑白反色;禁用 class 清单与交付自检清单都在该文档,交付前逐项过。

## 结构约定

- 自建组件住 `src/components/`(扁平皮肤,交互原语用 Radix,无障碍由 Radix 承担)。
- 一区一目录:`src/areas/<area>/`(`index.tsx` 导出区的路由与导航条目 + `<Area>Area.tsx` 本区界面 + `queries.ts` 本区服务端状态)。注册表 `src/areas/registry.ts` 用 `import.meta.glob` 自动汇总:**新增一区只增目录,不改任何共享文件**。
- API 类型从后端 OpenAPI schema 生成(`npm run gen:api` → `src/api/generated`),**禁止手抄接口类型**。
- 服务端数据一律 TanStack Query(按区分文件,不塞进全局大文件);跨组件 UI 状态才用 zustand(`src/store/ui.ts`)。
- 信息架构:六区(会话/知识库/生成物/图谱/冲突/题库)+ 设置,默认路由 = 会话;布局见 `docs/architecture.md`。
