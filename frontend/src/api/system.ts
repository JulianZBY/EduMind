/**
 * 系统级服务端状态（健康探测）：不属于任何业务区，放在 api/ 下。
 *
 * 响应体类型取自后端 OpenAPI 生成的 schema（`PingResponse`），不手抄字段——
 * 调用方只需知道「可达 / 不可达」，所以只把类型交给 `apiRequest`，不在界面里读字段。
 */
import { useQuery } from '@tanstack/react-query'
import { apiRequest } from './client'
import type { PingApiV1PingGetData, PingApiV1PingGetResponse } from './generated'

/** URL 也来自生成的 schema，避免前后端路径各写一份。 */
const pingUrl: PingApiV1PingGetData['url'] = '/api/v1/ping'

export const systemKeys = {
  ping: ['system', 'ping'] as const,
}

export function useServiceStatus() {
  return useQuery({
    queryKey: systemKeys.ping,
    queryFn: ({ signal }) => apiRequest<PingApiV1PingGetResponse>(pingUrl, { signal }),
    retry: 1,
    staleTime: 15_000,
  })
}
