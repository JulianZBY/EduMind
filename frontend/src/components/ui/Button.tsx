import { Slot } from '@radix-ui/react-slot'
import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type ButtonVariant = 'default' | 'accent'
export type ButtonSize = 'sm' | 'md'

/**
 * 四态（风格文档第 2/3 节）：
 * - 默认：白底黑字，`border-2 border-black` + `rounded-none`
 * - 悬停：黑白反色（`hover:bg-black hover:text-white`），不做位移、不加阴影
 * - 聚焦：`focus-visible:outline-2 outline-offset-2 outline-black`
 * - 禁用：边框 2px→1px + 文字降为 `text-black/40`（不用灰色填充），且不响应指针
 */
const base =
  'inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-none border-2 border-black font-bold outline-none transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black disabled:pointer-events-none disabled:border disabled:border-black/40 disabled:bg-transparent disabled:text-black/40'

const variants: Record<ButtonVariant, string> = {
  default: 'bg-white text-black hover:bg-black hover:text-white',
  /** 关键动作与破坏性动作的确认按钮；强调色上只放黑字。 */
  accent: 'bg-[#ff3366] text-black hover:bg-black hover:text-white',
}

const sizes: Record<ButtonSize, string> = {
  sm: 'h-7 px-2 text-xs',
  md: 'h-8 px-3 text-sm',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** 把按钮皮肤套到别的元素上（如 <Link>），交互语义由目标元素承担。 */
  asChild?: boolean
}

export function Button({
  variant = 'default',
  size = 'md',
  asChild = false,
  className,
  type = 'button',
  ...props
}: ButtonProps) {
  const classes = cn(base, variants[variant], sizes[size], className)
  if (asChild) {
    return <Slot className={classes} {...props} />
  }
  return <button type={type} className={classes} {...props} />
}
