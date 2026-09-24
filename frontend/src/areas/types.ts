import type { RouteObject } from 'react-router'

/**
 * 一个区对外暴露的全部内容：**导航条目**（label / path / order）与**路由**。
 *
 * 扩展点约定（票 04 硬要求，为 09/10/12/13 并行开发留缝）：
 * - 一区一目录：`src/areas/<area>/`，目录里的 `index.tsx` 默认导出本模块；
 * - 新增一区 = 新建该目录 + 默认导出一个 AreaModule，**不需要改任何共享文件**
 *   （注册表 src/areas/registry.ts 用 import.meta.glob 自动汇总）；
 * - 本区的服务端状态 hooks 住 `src/areas/<area>/queries.ts`，不要塞进全局大文件；
 * - 本区专属界面状态住 `src/areas/<area>/store.ts`（有需要才建）。
 *
 * `id` 用普通字符串而非联合类型：新增一区不该被迫改动任何共享文件。
 */
export interface AreaModule {
  /** 稳定标识：与目录名一致，同时用作路由 id 前缀与 query key 前缀。 */
  readonly id: string
  /** 区名：面向教师的文案，照 CONTEXT.md 第 1 节的六区与设置。 */
  readonly label: string
  /** 一级路由路径（绝对路径）。 */
  readonly path: string
  /** 区级导航顺序（工作台上的先后）。 */
  readonly order: number
  /** 默认落脚区：全站只能有一个（票 04 定为备课会话）。 */
  readonly isDefault?: boolean
  /** 一句话说明：导航提示与空状态共用（编辑密度文案）。 */
  readonly tagline: string
  /** 本区路由：深层路由（选中对象）也挂在这里，URL 即路由。 */
  readonly routes: RouteObject[]
}
