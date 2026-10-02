/**
 * 设置区的服务端状态（TanStack Query）。
 * 约定：query key 以 `settingsKeys.all` 打头，hooks 只住本文件。
 *
 * 写入用 PUT 的响应直接回填缓存（后端返回的就是写入后的完整生效配置），
 * 所以「改完立刻看到新值」不依赖重新拉取，也不依赖重启。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  CreateProviderInstanceApiV1SettingsProvidersPostResponses,
  ProviderInstanceCreate,
  ProviderInstanceUpdate,
  ReadCatalogApiV1SettingsCatalogGetResponses,
  ReadSettingsApiV1SettingsGetResponses,
  SettingsUpdate,
  UpdateSettingsApiV1SettingsPutResponses,
} from '../../api/generated'
import type { ApiResponseBody } from '../../api/client'
import { API_BASE_URL, apiErrorMessage, apiRequest } from '../../api/client'

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

/** 把接口错误翻成教师能读的一句话（共用提取器；400/503 的 `detail.message` 本身就是文案）。 */
export function settingsErrorMessage(error: unknown): string {
  const status = (error as { status?: unknown } | null)?.status
  const fallback = typeof status === 'number' ? `接口返回 ${status}，请重试。` : '请求失败，请重试。'
  return apiErrorMessage(error, fallback)
}

/** 当前生效设置：每项带来源，Key 只有掩码。 */
export function useSettingsQuery() {
  return useQuery({
    queryKey: settingsKeys.view(),
    queryFn: ({ signal }) => apiRequest<SettingsViewBody>(`${API_BASE_URL}/settings`, { signal }),
  })
}

/** 未配置状态（ProviderMissingNotice 的数据源）：还没加供应商，以及能力实现里未就绪的项。 */
export interface ProviderMissingState {
  /** 还没添加任何供应商：对话、生成、知识提取都要对话模型。 */
  providersMissing: boolean
  /** 能力实现里未就绪的项（asr / search 等），reason 是面向教师的说法。 */
  notReady: Array<{ key: string; label: string; reason: string }>
}

export function useProviderMissingState(): ProviderMissingState {
  const view = useSettingsQuery()
  return {
    providersMissing: Boolean(view.isSuccess && view.data.provider_instances.length === 0),
    notReady: (view.data?.capabilities ?? [])
      .filter((item) => !item.ready && item.reason)
      .map((item) => ({ key: item.key, label: item.label, reason: item.reason })),
  }
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

// ---- 供应商实例（多供应商并存：添加 / 改 / 删）----

export type ProviderInstanceBody = ApiResponseBody<
  CreateProviderInstanceApiV1SettingsProvidersPostResponses,
  200
>

/** 添加供应商：目录家只填 provider + Key；自定义服务另填名称 / 地址 / 模型。 */
export function useAddProviderInstance() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ProviderInstanceCreate) =>
      apiRequest<ProviderInstanceBody>(`${API_BASE_URL}/settings/providers`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: settingsKeys.view() }),
  })
}

/** 改供应商：名称 / 地址 / 模型 / Key / 设为默认；成功后重取生效配置。 */
export function useUpdateProviderInstance() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ instanceId, patch }: { instanceId: string; patch: ProviderInstanceUpdate }) =>
      apiRequest<ProviderInstanceBody>(
        `${API_BASE_URL}/settings/providers/${encodeURIComponent(instanceId)}`,
        { method: 'PATCH', body: patch },
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: settingsKeys.view() }),
  })
}

/** 删除供应商：响应就是删除后的完整生效配置，直接回填缓存。 */
export function useDeleteProviderInstance() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (instanceId: string) =>
      apiRequest<SettingsViewBody>(
        `${API_BASE_URL}/settings/providers/${encodeURIComponent(instanceId)}`,
        { method: 'DELETE' },
      ),
    onSuccess: (view) => queryClient.setQueryData(settingsKeys.view(), view),
  })
}

/** 刷新该家的模型清单：重新调 /v1/models 并整表替换缓存；成功后重取生效配置。 */
export function useRefreshProviderModels() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (instanceId: string) =>
      apiRequest<ProviderInstanceBody>(
        `${API_BASE_URL}/settings/providers/${encodeURIComponent(instanceId)}/refresh-models`,
        { method: 'POST' },
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: settingsKeys.view() }),
  })
}
