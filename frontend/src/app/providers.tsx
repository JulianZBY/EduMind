import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { ToastProvider } from '../components/ui/Toast'
import { createQueryClient } from './queryClient'

/**
 * 全局接线：TanStack Query（服务端状态）+ 轻提示队列（zustand）。
 * devtools 只在开发期挂上，不参与生产构建（import.meta.env.DEV 被静态替换）。
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient)

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
      {import.meta.env.DEV ? <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-left" /> : null}
    </QueryClientProvider>
  )
}
