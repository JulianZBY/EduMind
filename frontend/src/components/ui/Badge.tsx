import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type BadgeTone = 'outline' | 'solid' | 'accent'

const base =
  'inline-flex select-none items-center gap-1 whitespace-nowrap rounded-none border-2 border-black px-1.5 py-0.5 text-xs'

const tones: Record<BadgeTone, string> = {
  outline: 'bg-white text-black',
  solid: 'bg-black text-white',
  /** 强调色底只放黑字（风格文档第 1 节）。 */
  accent: 'bg-[#ff3366] text-black',
}

export interface BadgeProps {
  tone?: BadgeTone
  children: ReactNode
  className?: string
  /** 传了 onClick 才是可交互标签：此时四态齐全（默认/悬停反色/聚焦可见/禁用降级）。 */
  onClick?: () => void
  disabled?: boolean
  title?: string
}

export function Badge({ tone = 'outline', children, className, onClick, disabled, title }: BadgeProps) {
  if (!onClick) {
    return (
      <span title={title} className={cn(base, tones[tone], className)}>
        {children}
      </span>
    )
  }

  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        base,
        tones[tone],
        'outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black disabled:pointer-events-none disabled:border disabled:border-black/40 disabled:bg-transparent disabled:text-black/40',
        className,
      )}
    >
      {children}
    </button>
  )
}
