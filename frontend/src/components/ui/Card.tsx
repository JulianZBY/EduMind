import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/cn'

/**
 * 卡片：一切容器都是 `border-2 border-black` + `rounded-none`，层次靠边线与留白，不用阴影/灰底。
 * 四态：默认无装饰；`interactive` 时给整卡黑白反色悬停 + 可见聚焦；`disabled` 时降为 1px 边线 + 文字弱化。
 */
const shell = 'rounded-none border-2 border-black bg-white text-black'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean
  disabled?: boolean
}

export function Card({ interactive = false, disabled = false, className, ...props }: CardProps) {
  const interactiveClasses =
    interactive && !disabled
      ? 'cursor-pointer outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black'
      : ''
  const disabledClasses = disabled ? 'border border-black/40 text-black/40' : ''
  return (
    <div
      aria-disabled={disabled || undefined}
      tabIndex={interactive && !disabled ? 0 : undefined}
      className={cn(shell, interactiveClasses, disabledClasses, className)}
      {...props}
    />
  )
}

export interface CardHeaderProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title: ReactNode
  meta?: ReactNode
  actions?: ReactNode
}

export function CardHeader({ title, meta, actions, className, ...props }: CardHeaderProps) {
  return (
    <header
      className={cn(
        'flex flex-wrap items-center justify-between gap-2 border-b-2 border-black px-3 py-2',
        className,
      )}
      {...props}
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-sm font-bold">{title}</h2>
        {meta ? <span className="text-xs text-black/60">{meta}</span> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  )
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('px-3 py-2 text-sm', className)} {...props} />
}

export function CardFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex items-center justify-end gap-2 border-t-2 border-black px-3 py-2', className)}
      {...props}
    />
  )
}
