/**
 * 设置区的服务端状态（TanStack Query）。
 * 约定：query key 以 `settingsKeys.all` 打头，hooks 只住本文件。
 *
 * 写入用 PUT 的响应直接回填缓存（后端返回的就是写入后的完整生效配置），
 * 所以「改完立刻看到新值」不依赖重新拉取，也不依赖重启。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  ReadCatalogApiV1SettingsCatalogGetResponses,
  ReadSettingsApiV1SettingsGetResponses,
  SettingsUpdate,
  UpdateSettingsApiV1SettingsPutResponses,
} from '../../api/generated'
import type { ApiResponseBody } from '../../api/client'
import { API_BASE_URL, apiRequest } from '../../api/client'

/** 读取与写入共用同一份响应形状（读取接口的 200 体）。 */
export type SettingsViewBody = ApiResponseBody<ReadSettingsApiV1SettingsGetResponses, 200>
export type SettingsCatalogBody = ApiResponseBody<ReadCatalogApiV1SettingsCatalogGetResponses, 200>
type UpdateResponseBody = ApiResponseBody<UpdateSettingsApiV1SettingsPutResponses, 200>

export const settingsKeys = {
  all: ['settings'] as const,
  view: () => ['settings', 'view'] as const,
  catalog: () => ['settings', 'catalog'] as const,
}

/**
 * 组装写入补丁：Key 字段名由目录决定（供应商的 `key_field`、能力实现需要哪个 Key），
 * 故按动态键组装。断言安全——键只可能来自后端给的目录字段名，而服务端只用登记过的项。
 */
export function settingsPatch(entries: Record<string, string | undefined>): SettingsUpdate {
  const patch: Record<string, string> = {}
  for (const [key, value] of Object.entries(entries)) {
    if (value !== undefined) patch[key] = value
  }
  return patch as SettingsUpdate
}

/** 把接口错误翻成教师能读的一句话（400 的 `detail.message` 本身就是面向教师的文案）。 */
export function settingsErrorMessage(error: unknown): string {
  const payload = (error as { payload?: unknown } | null)?.payload
  const detail = (payload as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof (detail as { message?: unknown }).message === 'string') {
    return (detail as { message: string }).message
  }
  const status = (error as { status?: unknown } | null)?.status
  return typeof status === 'number' ? `接口返回 ${status}，请重试。` : '请求失败，请重试。'
}

/** 当前生效设置：每项带来源，Key 只有掩码。 */
export function useSettingsQuery() {
  return useQuery({
    queryKey: settingsKeys.view(),
    queryFn: ({ signal }) => apiRequest<SettingsViewBody>(`${API_BASE_URL}/settings`, { signal }),
  })
}

/** 可选目录：供应商、能力实现、任务清单（下拉的唯一出处）。 */
export function useSettingsCatalogQuery() {
  return useQuery({
    queryKey: settingsKeys.catalog(),
    queryFn: ({ signal }) =>
      apiRequest<SettingsCatalogBody>(`${API_BASE_URL}/settings/catalog`, { signal }),
  })
}

/** 写入设置：只传要改的项；成功后用响应回填缓存，改动立即生效。 */
export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch: SettingsUpdate) =>
      apiRequest<UpdateResponseBody>(`${API_BASE_URL}/settings`, { method: 'PUT', body: patch }),
    onSuccess: (view) => queryClient.setQueryData(settingsKeys.view(), view),
  })
}
