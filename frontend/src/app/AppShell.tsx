import { Suspense } from 'react'
import { Outlet } from 'react-router'
import { AboutDialog } from './AboutDialog'
import { AppHeader } from './AppHeader'
import { AreaRail } from './AreaRail'
import { ServiceStatusDrawer } from './ServiceStatusDrawer'

/** 区 chunk 拉取时的占位：与各区加载态同一套扁平语言（role=status，黑描边进度条）。 */
function AreaLoading() {
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-start gap-2 px-4 py-6">
      <p className="text-sm text-black">正在进入功能区…</p>
      <div aria-hidden="true" className="h-2 w-32 rounded-none border-2 border-black">
        <div className="h-full w-1/2 bg-black" />
      </div>
    </div>
  )
}

/**
 * 应用外壳：顶栏（品牌 + 服务状态 + 关于 + 更多）+ 区级导航 + 当前区。
 * 全高布局、白底黑字，页面四周一圈黑框（`border-2 border-black`），分隔一律
 * `border-b-2 border-black`（工作台密度）；主区高度受限（`min-h-0`），滚动只发生在
 * 各区自己的内容列里，页面本身不滚。
 */
export function AppShell() {
  return (
    <div className="flex h-dvh w-full flex-col border-2 border-black bg-white text-black">
      <AppHeader />
      <div className="flex min-h-0 flex-1">
        <AreaRail />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {/* 内容列的 Suspense 边界：区是懒加载的（M6），切区时外壳不动，这里先显示占位。 */}
          <Suspense fallback={<AreaLoading />}>
            <Outlet />
          </Suspense>
        </div>
      </div>
      <ServiceStatusDrawer />
      <AboutDialog />
    </div>
  )
}
