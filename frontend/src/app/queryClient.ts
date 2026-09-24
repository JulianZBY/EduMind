import { QueryClient } from '@tanstack/react-query'

/**
 * 服务端状态的唯一缓存（ADR-0005）：TanStack Query 是服务端数据的唯一通路。
 * 默认值只做保守设置：失败重试一次、窗口聚焦不自动重拉、30 秒内视为新鲜。
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  })
}
