import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/cn'

/**
 * 下拉菜单（Radix DropdownMenu：键盘导航、Esc 关闭、焦点回退由原语承担）。
 * 条目四态：默认白底黑字 / 悬停与键盘高亮黑白反色 / 聚焦可见轮廓 / 禁用降为 1px 边线与弱化文字。
 */
export function DropdownMenu(props: ComponentProps<typeof DropdownMenuPrimitive.Root>) {
  return <DropdownMenuPrimitive.Root {...props} />
}

export function DropdownMenuTrigger(props: ComponentProps<typeof DropdownMenuPrimitive.Trigger>) {
  return <DropdownMenuPrimitive.Trigger {...props} />
}

export function DropdownMenuContent({
  className,
  sideOffset = 4,
  align = 'end',
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        sideOffset={sideOffset}
        align={align}
        className={cn(
          'z-50 min-w-44 rounded-none border-2 border-black bg-white p-0 text-black outline-none',
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  )
}

export function DropdownMenuItem({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Item>) {
  return (
    <DropdownMenuPrimitive.Item
      className={cn(
        'flex cursor-pointer items-center justify-between gap-3 rounded-none border-b-2 border-black px-3 py-1.5 text-sm',
        'outline-none transition-colors duration-150 data-[highlighted]:bg-black data-[highlighted]:text-white',
        'data-[disabled]:pointer-events-none data-[disabled]:border-b data-[disabled]:border-black/40 data-[disabled]:text-black/40',
        'last:border-b-2',
        className,
      )}
      {...props}
    />
  )
}

export function DropdownMenuLabel({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Label>) {
  return (
    <DropdownMenuPrimitive.Label
      className={cn('border-b-2 border-black px-3 py-1.5 text-xs font-bold text-black/60', className)}
      {...props}
    />
  )
}

export function DropdownMenuSeparator({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Separator>) {
  return (
    <DropdownMenuPrimitive.Separator className={cn('h-0 border-t-2 border-black', className)} {...props} />
  )
}
