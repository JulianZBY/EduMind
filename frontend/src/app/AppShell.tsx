import { Outlet } from 'react-router'
import { AboutDialog } from './AboutDialog'
import { AppHeader } from './AppHeader'
import { AreaRail } from './AreaRail'
import { ServiceStatusDrawer } from './ServiceStatusDrawer'

/**
 * 应用外壳：顶栏（品牌 + 服务状态 + 关于 + 更多）+ 区级导航 + 当前区。
 * 全高布局、白底黑字，分隔一律 `border-b-2 border-black`（工作台密度）。
 */
export function AppShell() {
  return (
    <div className="flex h-dvh w-full flex-col bg-white text-black">
      <AppHeader />
      <div className="flex min-h-0 flex-1">
        <AreaRail />
        <div className="flex min-w-0 flex-1 flex-col">
          <Outlet />
        </div>
      </div>
      <ServiceStatusDrawer />
      <AboutDialog />
    </div>
  )
}
