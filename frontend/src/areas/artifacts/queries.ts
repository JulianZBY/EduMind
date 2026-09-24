/**
 * 生成物区的服务端状态（TanStack Query）：版本列表 / 版本详情 / 修改意见 / 按需生成。
 *
 * **版本数据只有一个事实源**（CONTEXT.md 第 3 节、ADR-0002）：票 07 的三个版本端点。
 * 备课会话区的生成物面板与生成物区共用本文件的 hooks 与 query key（同一份缓存），
 * 所以两处的当前版本、历史版本、版本号必然一致——浏览器里不存在第二份版本列表。
 *
 * 请求地址、请求体与响应体类型全部取自生成的 schema（ADR-0005：仓库内不手抄接口类型）；
 * 业务判断（哪一版是基线、修改意见走哪个端点）住 `narrowing.ts` 的纯函数，便于脱离 React 核对。
 */
import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import type { ApiResponseBody } from '../../api/client'
import type {
  ArtifactVersionGroup,
  ArtifactVersionItem,
  DownloadArtifactVersionApiV1ArtifactsVersionIdDownloadGetData,
  ExamGenerateRequest,
  GenerateExamPaperApiV1ExamGeneratePostData,
  GenerateExamPaperApiV1ExamGeneratePostResponse,
  GenerateInteractiveApiV1InteractiveGeneratePostData,
  GenerateInteractiveApiV1InteractiveGeneratePostResponse,
  GetArtifactVersionApiV1ArtifactsVersionIdGetData,
  GetArtifactVersionApiV1ArtifactsVersionIdGetResponses,
  InteractiveGenerateRequest,
  ListArtifactVersionsApiV1SessionsSessionIdArtifactsGetData,
  ListArtifactVersionsApiV1SessionsSessionIdArtifactsGetResponses,
  ListSessionsApiV1SessionsGetData,
  ListSessionsApiV1SessionsGetResponses,
} from '../../api/generated'
import { buildRevisionRequest } from './narrowing'
import type { ArtifactType, RevisionInput } from './narrowing'

export type { ArtifactType }
/** 版本行与版本组：形状直接来自生成的 schema（不另抄一份）。 */
export type ArtifactVersion = ArtifactVersionItem
export type ArtifactGroup = ArtifactVersionGroup

/** 版本列表 / 版本详情 / 会话列表的响应体。 */
export type ArtifactListBody = ApiResponseBody<
  ListArtifactVersionsApiV1SessionsSessionIdArtifactsGetResponses,
  200
>
export type ArtifactDetailBody = ApiResponseBody<
  GetArtifactVersionApiV1ArtifactsVersionIdGetResponses,
  200
>
export type ArtifactSessionListBody = ApiResponseBody<ListSessionsApiV1SessionsGetResponses, 200>

/** 地址取自生成的 schema（ADR-0005：仓库内不手抄接口路径）。 */
const sessionArtifactsTemplate: ListArtifactVersionsApiV1SessionsSessionIdArtifactsGetData['url'] =
  '/api/v1/sessions/{session_id}/artifacts'
const versionUrlTemplate: GetArtifactVersionApiV1ArtifactsVersionIdGetData['url'] =
  '/api/v1/artifacts/{version_id}'
const versionDownloadTemplate: DownloadArtifactVersionApiV1ArtifactsVersionIdDownloadGetData['url'] =
  '/api/v1/artifacts/{version_id}/download'
const sessionsUrl: ListSessionsApiV1SessionsGetData['url'] = '/api/v1/sessions'
const examGenerateUrl: GenerateExamPaperApiV1ExamGeneratePostData['url'] = '/api/v1/exam/generate'
const interactiveGenerateUrl: GenerateInteractiveApiV1InteractiveGeneratePostData['url'] =
  '/api/v1/interactive/generate'

/** 版本列表地址：`artifact_type` 非空时只看某一类生成物（某一条时间线）。 */
export function sessionArtifactsUrl(sessionId: string, artifactType?: ArtifactType): string {
  const base = sessionArtifactsTemplate.replace('{session_id}', encodeURIComponent(sessionId))
  return artifactType
    ? `${base}?${new URLSearchParams({ artifact_type: artifactType }).toString()}`
    : base
}

/** 某一版文件的地址：默认附下载头；`openInTab` 时不附（互动内容在新标签页直接打开试用）。 */
export function artifactDownloadUrl(
  versionId: string,
  options: { openInTab?: boolean } = {},
): string {
  const base = versionDownloadTemplate.replace('{version_id}', encodeURIComponent(versionId))
  return options.openInTab ? `${base}?inline=true` : base
}

// ---- 数据层（不依赖 React，可单独调用）----

/** 某次备课的全部生成物版本（按类别分组，含当前版本与全部历史版本）。 */
export async function fetchArtifactVersions(
  sessionId: string,
  artifactType?: ArtifactType,
  signal?: AbortSignal,
): Promise<ArtifactListBody> {
  return apiRequest<ArtifactListBody>(sessionArtifactsUrl(sessionId, artifactType), { signal })
}

/** 某一版的详情：版本号、产出方式、基线版本与**内容快照**（回看历史版本靠它）。 */
export async function fetchArtifactVersion(
  versionId: string,
  signal?: AbortSignal,
): Promise<ArtifactDetailBody> {
  return apiRequest<ArtifactDetailBody>(
    versionUrlTemplate.replace('{version_id}', encodeURIComponent(versionId)),
    { signal },
  )
}

/** 备课会话列表（生成物区按会话分组用）；`q` 按标题过滤，与服务端同一语义。 */
export async function fetchArtifactSessions(
  keyword = '',
  signal?: AbortSignal,
): Promise<ArtifactSessionListBody> {
  const trimmed = keyword.trim()
  const url = trimmed
    ? `${sessionsUrl}?${new URLSearchParams({ q: trimmed }).toString()}`
    : sessionsUrl
  return apiRequest<ArtifactSessionListBody>(url, { signal })
}

/** 五个修改端点共有的出参：新版本标识 + 新文件名（内容字段各端点不同，调用方按需读）。 */
export interface ArtifactRevisionOutcome {
  readonly versionId: string | null
  readonly version: number | null
  readonly filename: string
  /** 试卷修改时会顺带把改后的题目写进题库（其余类别为 null）。 */
  readonly bankSaved: number | null
}

function toRevisionOutcome(payload: {
  version_id?: string | null
  version?: number | null
  filename: string
  bank_saved?: number
}): ArtifactRevisionOutcome {
  return {
    versionId: payload.version_id ?? null,
    version: payload.version ?? null,
    filename: payload.filename,
    bankSaved: payload.bank_saved ?? null,
  }
}

/**
 * 按修改意见重做**所选生成物**：请求体里只有这一版的内容 + 修改意见 + 基线版本，
 * 因此只影响所选生成物（其它类别一个版本都不多），且产出的是版本号更高的新版本。
 */
export async function reviseArtifact(input: RevisionInput): Promise<ArtifactRevisionOutcome> {
  const plan = buildRevisionRequest(input)
  if (!plan.ok) throw new Error(plan.reason)
  const payload = await apiRequest<Parameters<typeof toRevisionOutcome>[0]>(plan.url, {
    method: 'POST',
    body: plan.body,
  })
  return toRevisionOutcome(payload)
}

/** 一键生成试卷：题目自动入题库并标注考查知识点；带会话时落一条试卷版本。 */
export async function generateExam(
  sessionId: string,
  intent: ExamGenerateRequest['intent'],
  n: number,
  signal?: AbortSignal,
): Promise<GenerateExamPaperApiV1ExamGeneratePostResponse> {
  const body: ExamGenerateRequest = { intent, n, session_id: sessionId }
  return apiRequest<GenerateExamPaperApiV1ExamGeneratePostResponse>(examGenerateUrl, {
    method: 'POST',
    body,
    signal,
  })
}

/** 按意图生成互动内容（单文件 HTML5）；带会话时落一条互动内容版本。 */
export async function generateInteractive(
  sessionId: string,
  intent: InteractiveGenerateRequest['intent'],
  signal?: AbortSignal,
): Promise<GenerateInteractiveApiV1InteractiveGeneratePostResponse> {
  const body: InteractiveGenerateRequest = { intent, session_id: sessionId }
  return apiRequest<GenerateInteractiveApiV1InteractiveGeneratePostResponse>(
    interactiveGenerateUrl,
    { method: 'POST', body, signal },
  )
}

// ---- query key ----

/**
 * query key 一律以 `artifactKeys.all` 打头。
 * `sessionArtifacts` 是**版本列表的唯一 key 前缀**：备课会话区与生成物区共用它，
 * 因此两处的版本数据不可能不一致（同一个缓存条目、同一个端点）。
 */
export const artifactKeys = {
  all: ['artifacts'] as const,
  sessionArtifacts: () => [...artifactKeys.all, 'session-artifacts'] as const,
  /** 某次备课的版本列表；`artifactType` 为空 = 全部类别 */
  sessionArtifact: (sessionId: string, artifactType?: ArtifactType) =>
    [...artifactKeys.sessionArtifacts(), sessionId, artifactType ?? '全部'] as const,
  versions: () => [...artifactKeys.all, 'version'] as const,
  version: (versionId: string) => [...artifactKeys.versions(), versionId] as const,
  sessionLists: () => [...artifactKeys.all, 'sessions'] as const,
  sessionList: (keyword: string) => [...artifactKeys.sessionLists(), keyword] as const,
}

// ---- hooks 层 ----

/**
 * 某次备课的全部生成物版本。挂载即重取：刚生成 / 刚修改完再进来必须看到最新版本，
 * 不能被缓存挡住；备课会话区的并排预览与生成物区的版本时间线用的是同一个 hook。
 */
export function useSessionArtifacts(sessionId: string | null) {
  return useQuery({
    queryKey: artifactKeys.sessionArtifact(sessionId ?? ''),
    queryFn: ({ signal }) => fetchArtifactVersions(sessionId ?? '', undefined, signal),
    enabled: Boolean(sessionId),
    refetchOnMount: 'always',
  })
}

/** 某一版的详情（含内容快照）。404 = 这一版不在了，要立刻呈现，不靠重试掩盖。 */
export function useArtifactVersion(versionId: string | null) {
  return useQuery({
    queryKey: artifactKeys.version(versionId ?? ''),
    queryFn: ({ signal }) => fetchArtifactVersion(versionId ?? '', signal),
    enabled: Boolean(versionId),
    retry: false,
  })
}

/** 备课会话列表（生成物区按会话分组用）：选中会话前先知道有哪些备课。 */
export function useArtifactSessions(keyword = '') {
  return useQuery({
    queryKey: artifactKeys.sessionList(keyword),
    queryFn: ({ signal }) => fetchArtifactSessions(keyword, signal),
    placeholderData: keepPreviousData,
    refetchOnMount: 'always',
  })
}

/** 一次备课的版本概览（侧栏计数用）：走同一个版本端点，不另造统计口径。 */
export interface SessionArtifactSummary {
  readonly sessionId: string
  readonly totalVersions: number
  readonly groups: readonly ArtifactGroup[]
  readonly isPending: boolean
  readonly isError: boolean
}

export function useSessionArtifactSummaries(sessionIds: readonly string[]): SessionArtifactSummary[] {
  return useQueries({
    queries: sessionIds.map((sessionId) => ({
      queryKey: artifactKeys.sessionArtifact(sessionId),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        fetchArtifactVersions(sessionId, undefined, signal),
      refetchOnMount: 'always' as const,
    })),
    combine: (results) =>
      results.map((result, index) => ({
        sessionId: sessionIds[index] ?? '',
        totalVersions: (result.data?.groups ?? []).reduce(
          (total, group) => total + group.versions.length,
          0,
        ),
        groups: result.data?.groups ?? [],
        isPending: result.isPending,
        isError: result.isError,
      })),
  })
}

/** 失效版本数据：修改 / 生成完让时间线、侧栏计数与并排预览一起跟上（同一份缓存）。 */
export function useInvalidateArtifacts() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: artifactKeys.sessionArtifacts() })
    void queryClient.invalidateQueries({ queryKey: artifactKeys.versions() })
  }
}

/** 修改所选生成物（只作用这一版，产出新版本）。 */
export function useReviseArtifact() {
  const invalidate = useInvalidateArtifacts()
  return useMutation({
    mutationFn: (input: RevisionInput) => reviseArtifact(input),
    onSuccess: invalidate,
  })
}

/** 一键生成试卷：题目入题库，试卷落一条新版本。 */
export function useGenerateExam(sessionId: string) {
  const invalidate = useInvalidateArtifacts()
  return useMutation({
    mutationFn: ({ intent, n }: { intent: ExamGenerateRequest['intent']; n: number }) =>
      generateExam(sessionId, intent, n),
    onSuccess: invalidate,
  })
}

/** 按意图生成互动内容：落一条新版本，可随即在新标签页打开试用。 */
export function useGenerateInteractive(sessionId: string) {
  const invalidate = useInvalidateArtifacts()
  return useMutation({
    mutationFn: (intent: InteractiveGenerateRequest['intent']) =>
      generateInteractive(sessionId, intent),
    onSuccess: invalidate,
  })
}
