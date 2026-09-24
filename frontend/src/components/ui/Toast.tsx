import * as ToastPrimitive from '@radix-ui/react-toast'
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { useUiStore } from '../../store/ui'
import { CloseIcon } from './icons'

/**
 * 轻提示（Radix Toast）：队列住在 zustand（跨组件界面状态），不在浏览器里存第二份事实源。
 * 悬停整条反色（黑白反色是唯一的「悬停」表达），关闭按钮四态齐全；
 * 强调色只用于边框与左侧标记，绝不在强调色上放白字。
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const toasts = useUiStore((state) => state.toasts)
  const dismissToast = useUiStore((state) => state.dismissToast)

  return (
    <ToastPrimitive.Provider duration={5000} swipeDirection="right">
      {children}
      {toasts.map((toast) => (
        <ToastPrimitive.Root
          key={toast.id}
          open
          onOpenChange={(open) => {
            if (!open) dismissToast(toast.id)
          }}
          className={cn(
            'group pointer-events-auto flex items-start justify-between gap-3 rounded-none border-2 border-black border-l-8 bg-white px-3 py-2 text-sm text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white',
            toast.tone === 'accent' ? 'border-l-[#ff3366]' : 'border-l-black',
          )}
        >
          <div className="flex flex-col gap-1">
            <ToastPrimitive.Title className="font-bold">{toast.title}</ToastPrimitive.Title>
            {toast.description ? (
              <ToastPrimitive.Description className="text-black/60 group-hover:text-white">
                {toast.description}
              </ToastPrimitive.Description>
            ) : null}
          </div>
          <ToastPrimitive.Close
            aria-label="关闭"
            className="shrink-0 rounded-none border-2 border-black p-0.5 text-black outline-none transition-colors duration-150 group-hover:border-white group-hover:text-white hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black disabled:pointer-events-none disabled:border disabled:border-black/40 disabled:text-black/40"
          >
            <CloseIcon />
          </ToastPrimitive.Close>
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="fixed right-4 bottom-4 z-60 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  )
}
