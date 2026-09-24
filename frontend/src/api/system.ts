/**
 * 系统级服务端状态（健康探测）：不属于任何业务区，放在 api/ 下。
 *
 * 注意：`/health` 不带 schema（后端用示例注解），故这里只断言「可达 / 不可达」，
 * 不去猜响应字段——猜字段就等于手抄接口类型（ADR-0005 禁止）。
 */
import { useQuery } from '@tanstack/react-query'
import { apiRequest } from './client'
import type { PingApiV1PingGetData } from './generated'

/** URL 也来自生成的 schema，避免前后端路径各写一份。 */
const pingUrl: PingApiV1PingGetData['url'] = '/api/v1/ping'

export const systemKeys = {
  ping: ['system', 'ping'] as const,
}

export function useServiceStatus() {
  return useQuery({
    queryKey: systemKeys.ping,
    queryFn: ({ signal }) => apiRequest<unknown>(pingUrl, { signal }),
    retry: 1,
    staleTime: 15_000,
  })
}
