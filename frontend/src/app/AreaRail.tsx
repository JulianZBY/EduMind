import { NavLink } from 'react-router'
import { areas } from '../areas/registry'
import { Button } from '../components/ui/Button'
import { MarkerIcon, RailToggleIcon } from '../components/ui/icons'
import { useUiStore } from '../store/ui'
import { cn } from '../lib/cn'

/**
 * 区级导航：条目直接来自各区自己导出的导航信息（registry 汇总），本组件不认识任何具体区。
 * 每个栏目一个独立矩形（`border-2 border-black`），矩形之间留间隙；当前项用「黑白反色 +
 * 强调色方块」表达，悬停一律黑白反色。
 */
export function AreaRail() {
  const collapsed = useUiStore((state) => state.railCollapsed)
  const toggleRail = useUiStore((state) => state.toggleRail)

  return (
    <nav
      aria-label="功能区"
      className={cn(
        'flex shrink-0 flex-col border-r-2 border-black',
        collapsed ? 'w-12' : 'w-52',
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b-2 border-black px-2 py-2">
        {collapsed ? null : <span className="text-xs font-bold text-black/60">六个区 + 设置</span>}
        <Button
          size="sm"
          aria-label={collapsed ? '展开区级导航' : '折叠区级导航'}
          aria-expanded={!collapsed}
          onClick={toggleRail}
        >
          <RailToggleIcon className="h-3.5 w-3.5" />
        </Button>
      </div>

      <ul className="flex flex-col gap-2 p-2">
        {areas.map((area) => (
          <li key={area.id}>
            <NavLink
              to={area.path}
              title={area.label}
              className={({ isActive }) =>
                cn(
                  'flex h-8 items-center gap-2 rounded-none border-2 border-black px-2 text-sm outline-none transition-colors duration-150',
                  'hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black',
                  isActive ? 'bg-black text-white' : 'bg-white text-black',
                  collapsed && 'justify-center px-0',
                )
              }
            >
              {({ isActive }) =>
                collapsed ? (
                  <>
                    <MarkerIcon className={cn('h-2.5 w-2.5', isActive && 'text-[#ff3366]')} />
                    <span className="sr-only">{area.label}</span>
                  </>
                ) : (
                  <>
                    <span
                      aria-hidden="true"
                      className={cn('h-2 w-2 shrink-0 bg-[#ff3366]', !isActive && 'invisible')}
                    />
                    <span>{area.label}</span>
                  </>
                )
              }
            </NavLink>
          </li>
        ))}
      </ul>

      {collapsed ? null : (
        <p className="mt-auto border-t-2 border-black px-3 py-2 text-xs leading-5 text-black/60">
          一区一件事：备课会话是日常主线，其余五区各自管一件事。
        </p>
      )}
    </nav>
  )
}
