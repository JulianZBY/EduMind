import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export interface EmptyStateProps {
  /** 编辑密度：大留白、字号高一档、单列窄容器，一次只做一件事。 */
  title: string
  description: string
  /** 补充一行机器口径（如选中的对象 id），工作台里可读可核对。 */
  meta?: ReactNode
  action?: ReactNode
  className?: string
}

export function EmptyState({ title, description, meta, action, className }: EmptyStateProps) {
  return (
    <div className={cn('mx-auto flex w-full max-w-md flex-col items-start gap-4 px-6 py-12', className)}>
      <span aria-hidden="true" className="h-4 w-4 rounded-none border-2 border-black bg-[#ff3366]" />
      <h2 className="text-xl font-bold text-black">{title}</h2>
      <p className="text-sm leading-6 text-black/60">{description}</p>
      {meta ? (
        <p className="w-full rounded-none border-2 border-black px-3 py-2 text-xs break-all text-black">
          {meta}
        </p>
      ) : null}
      {action ? <div className="flex flex-wrap items-center gap-2">{action}</div> : null}
    </div>
  )
}
