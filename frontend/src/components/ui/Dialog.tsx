import * as DialogPrimitive from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { Button } from './Button'
import { CloseIcon } from './icons'

export interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  /** 弹层宽度档位；面板一律白底 + `border-2 border-black` 划界。 */
  size?: 'sm' | 'md'
}

const sizes = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
} as const

/**
 * 弹层（Radix Dialog 承担键盘可达、焦点陷阱与 Esc 关闭；这里只做扁平皮肤）。
 * 遮罩不做半透明、不做模糊：面板边界用 `border-2 border-black` 划出（风格文档第 2 节），
 * 也不做位移动画，只保留纯色彩过渡。
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = 'md',
}: DialogProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40" />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <DialogPrimitive.Content
            aria-describedby={description ? undefined : undefined}
            className={cn(
              'flex max-h-[calc(100vh-4rem)] w-full flex-col rounded-none border-2 border-black bg-white text-black outline-none',
              sizes[size],
            )}
          >
            <header className="flex items-start justify-between gap-3 border-b-2 border-black px-4 py-3">
              <div className="flex flex-col gap-1">
                <DialogPrimitive.Title className="text-base font-bold">{title}</DialogPrimitive.Title>
                {description ? (
                  <DialogPrimitive.Description className="text-sm text-black/60">
                    {description}
                  </DialogPrimitive.Description>
                ) : null}
              </div>
              <DialogPrimitive.Close asChild>
                <Button size="sm" aria-label="关闭">
                  <CloseIcon />
                </Button>
              </DialogPrimitive.Close>
            </header>
            <div className="flex-1 overflow-auto px-4 py-3 text-sm leading-6">{children}</div>
            {footer ? (
              <footer className="flex flex-wrap items-center justify-end gap-2 border-t-2 border-black px-4 py-3">
                {footer}
              </footer>
            ) : null}
          </DialogPrimitive.Content>
        </div>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
