/**
 * 接口调用基础设施：唯一的事实源是后端 OpenAPI（见 src/api/generated，由 npm run gen:api 生成）。
 *
 * 纪律（ADR-0005 / 票 04）：仓库内**不手抄接口类型**——请求体与响应体的类型一律从
 * `src/api/generated` 里取（下面给出取法），本文件只提供传输、错误包装与取消信号。
 */
import type { ClientOptions } from './generated'

/** dev 下由 vite 代理到后端（见 vite.config.ts），生产由同源反向代理承担。 */
export const API_BASE_URL = '/api/v1'

/** 生成类型里带的基地址形状，防止手写字符串拼出越界地址。 */
export type ApiBaseUrl = ClientOptions['baseUrl']

/**
 * 从操作响应类型里取某个状态码的响应体。
 * 用法：`ApiResponseBody<PingApiV1PingGetResponses, 200>`（类型全部来自生成的 schema）。
 */
export type ApiResponseBody<TResponses, TStatus extends keyof TResponses> = TResponses[TStatus]

export class ApiError extends Error {
  readonly status: number
  readonly payload: unknown

  constructor(status: number, payload: unknown, message?: string) {
    super(message ?? `接口返回 ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

export interface ApiCallOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  /** JSON 对象或 FormData（上传用）；两者都不传则无请求体。 */
  body?: unknown
  signal?: AbortSignal
  headers?: Record<string, string>
}

async function readPayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    return response.json()
  }
  return response.text()
}

/**
 * 发一次请求。响应体类型由调用方按生成的 schema 给出（`TData`），不在这里手写形状。
 */
export async function apiRequest<TData>(
  url: string,
  options: ApiCallOptions = {},
): Promise<TData> {
  const { method = 'GET', body, signal, headers } = options
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData
  const response = await fetch(url, {
    method,
    signal,
    headers: {
      Accept: 'application/json',
      ...(body !== undefined && !isFormData ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : isFormData ? (body as FormData) : JSON.stringify(body),
  })

  const payload = await readPayload(response)
  if (!response.ok) {
    throw new ApiError(response.status, payload)
  }
  return payload as TData
}
