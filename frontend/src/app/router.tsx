import { redirect } from 'react-router'
import type { RouteObject } from 'react-router'
import { DEFAULT_AREA_PATH, areas } from '../areas/registry'
import { AppShell } from './AppShell'
import { NotFoundPage } from './NotFoundPage'

/**
 * 全站路由表（纯数据，可在没有浏览器的环境里被检查脚本加载）。
 *
 * - 默认落脚区：根路径 `/` 由路由自己的 loader 重定向到备课会话（票 04 的默认路由口径，
 *   做成 loader 而不是组件，是为了让「默认路由」也能被 check:routes 直接断言）；
 * - 各区的路由由本区自己导出（见 src/areas/<area>/index.tsx），这里只做汇总，
 *   不认识任何具体区的页面；
 * - 浏览器路由实例在 main.tsx 里由这份表创建（createBrowserRouter）。
 */
export const routeObjects: RouteObject[] = [
  {
    id: 'app-shell',
    path: '/',
    element: <AppShell />,
    children: [
      { id: 'default-area', index: true, loader: () => redirect(DEFAULT_AREA_PATH) },
      ...areas.flatMap((area) => area.routes),
      { id: 'not-found', path: '*', element: <NotFoundPage /> },
    ],
  },
]
