import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

/**
 * 工作台布局（工作台密度：紧凑行高、贴边分隔线、无装饰留白）。
 * 四区是「二级侧栏 + 主区」，看板两区（图谱 / 冲突审核）只渲染 MainPanel 直铺。
 */
export function Workbench({ sidebar, children }: { sidebar: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1">
      {sidebar}
      {children}
    </div>
  )
}

export interface WorkbenchSidebarProps {
  /** 侧栏标题：用区名或「列表」类术语。 */
  title: string
  meta?: ReactNode
  actions?: ReactNode
  children: ReactNode
}

export function WorkbenchSidebar({ title, meta, actions, children }: WorkbenchSidebarProps) {
  return (
    <aside aria-label={title} className="flex w-60 shrink-0 flex-col border-r-2 border-black">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-black px-3 py-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="text-sm font-bold">{title}</h2>
          {meta ? <span className="text-xs text-black/60">{meta}</span> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </aside>
  )
}

export interface MainPanelProps {
  /** 主区标题（区名）。 */
  title: string
  tagline?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}

export function MainPanel({ title, tagline, actions, children, className }: MainPanelProps) {
  return (
    <section className={cn('flex min-w-0 flex-1 flex-col', className)}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-black px-3 py-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h1 className="text-sm font-bold">{title}</h1>
          {tagline ? <p className="text-xs text-black/60">{tagline}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </section>
  )
}
