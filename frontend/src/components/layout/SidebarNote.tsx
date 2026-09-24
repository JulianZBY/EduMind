import type { ReactNode } from 'react'

/** 二级侧栏里的清单说明：工作台密度（小字号、贴边留白），与主区编辑密度的空状态区分开。 */
export function SidebarNote({ children }: { children: ReactNode }) {
  return <p className="px-3 py-3 text-xs leading-5 text-black/60">{children}</p>
}
