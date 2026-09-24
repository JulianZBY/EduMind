import * as DialogPrimitive from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'
import { Button } from './Button'
import { CloseIcon } from './icons'

export interface DrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
  /** 抽屉从右侧滑入的宽度；内容区可滚动。 */
  width?: string
}

/**
 * 抽屉（Radix Dialog + 侧向布局）：与弹层共用无障碍行为（焦点陷阱 / Esc / 键盘可达）。
 * 页面与面板之间用 `border-l-2 border-black` 的不透明黑边隔断，不用半透明遮罩与模糊材质。
 */
export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  width = 'max-w-md',
}: DrawerProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40" />
        <div className="fixed inset-0 z-50 flex justify-end">
          <DialogPrimitive.Content
            className={`flex h-full w-full ${width} flex-col rounded-none border-l-2 border-black bg-white text-black outline-none`}
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
            <div className="flex-1 overflow-auto px-4 py-3 text-sm">{children}</div>
          </DialogPrimitive.Content>
        </div>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
