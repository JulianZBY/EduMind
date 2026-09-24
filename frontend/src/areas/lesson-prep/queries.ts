/**
 * 备课会话区的服务端状态（TanStack Query）：会话列表 / 历史 / 一轮对话 / 上传与参考资料绑定。
 *
 * 事实源在服务端（ADR-0002）：浏览器里没有、也不该有会话事实——浏览器侧会话存储已在票 04
 * 退场，本区不得再引入任何浏览器侧的会话事实源。本文件分两层：
 *
 * - **数据层**（`fetchSessions` / `createSession` / `sendTurn` …）是普通 async 函数：只发请求、
 *   返回生成的 schema 类型，可脱离 React 直接调用（验收时可拿真后端跑一遍）；
 * - **hooks 层**只做缓存、失效与乐观改写（乐观改写也在服务端事实回归时被覆盖）。
 *
 * query key 一律以 `lessonPrepKeys.all` 打头（票 04 的扩展点约定）。
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import type { ApiResponseBody } from '../../api/client'
import type {
  ChatApiV1ChatPostData,
  ChatApiV1ChatPostResponse,
  ChatRequest,
  DeleteSessionApiV1SessionsSessionIdDeleteResponse,
  DownloadFileApiV1FilesFilenameGetData,
  ListDocumentsApiV1DocumentsGetData,
  ListSessionsApiV1SessionsGetData,
  ListSessionsApiV1SessionsGetResponses,
  SessionCreateRequest,
  SessionHistoryApiV1SessionsSessionIdGetData,
  SessionHistoryApiV1SessionsSessionIdGetResponses,
  SessionSummary,
  SessionUpdateRequest,
  UploadDocumentApiV1DocumentsUploadPostData,
} from '../../api/generated'
import { readKnowledgeDocument, readKnowledgeDocuments } from './narrowing'
import type { KnowledgeDocument } from './narrowing'
import { artifactKeys } from '../artifacts/queries'

/** 会话摘要与消息形状都直接来自生成的 schema（ADR-0005 禁止手抄接口类型）。 */
export type { SessionSummary }

/** 追问粒度三档（CONTEXT.md「追问粒度」）：快速 / 标准 / 精细。 */
export type Granularity = NonNullable<SessionCreateRequest['granularity']>

/** 列表响应体与其中的一行：形状来自生成的 schema，不另抄一份。 */
export type SessionListBody = ApiResponseBody<ListSessionsApiV1SessionsGetResponses, 200>
/** 会话历史响应体与其中一条消息。 */
export type SessionHistoryBody = ApiResponseBody<
  SessionHistoryApiV1SessionsSessionIdGetResponses,
  200
>
export type SessionMessage = SessionHistoryBody['messages'][number]

/** 地址也取自生成的 schema（ADR-0005：仓库内不手抄接口路径）。 */
const sessionsUrl: ListSessionsApiV1SessionsGetData['url'] = '/api/v1/sessions'
const sessionUrlTemplate: SessionHistoryApiV1SessionsSessionIdGetData['url'] =
  '/api/v1/sessions/{session_id}'
const chatUrl: ChatApiV1ChatPostData['url'] = '/api/v1/chat'
const documentsUrl: ListDocumentsApiV1DocumentsGetData['url'] = '/api/v1/documents'
const documentUploadUrl: UploadDocumentApiV1DocumentsUploadPostData['url'] =
  '/api/v1/documents/upload'
const fileUrlTemplate: DownloadFileApiV1FilesFilenameGetData['url'] = '/api/v1/files/{filename}'

/** 会话地址（历史 / 重命名 / 删除 / 改设置共用）。 */
export function sessionDetailUrl(sessionId: string): string {
  return sessionUrlTemplate.replace('{session_id}', encodeURIComponent(sessionId))
}

/** 会话列表地址：`q` 交给服务端按标题过滤（会话列表检索），空关键词就是「全部会话」。 */
export function sessionListUrl(keyword = ''): string {
  const trimmed = keyword.trim()
  if (!trimmed) return sessionsUrl
  return `${sessionsUrl}?${new URLSearchParams({ q: trimmed }).toString()}`
}

/** 生成物文件地址：课件/教案/试卷走下载；互动内容可在新标签页直接打开试用（`inline=true`）。 */
export function artifactFileUrl(filename: string, options: { openInTab?: boolean } = {}): string {
  const base = fileUrlTemplate.replace('{filename}', encodeURIComponent(filename))
  return options.openInTab ? `${base}?inline=true` : base
}

// ---- 数据层（不依赖 React，可单独调用）----

/** 会话列表（最近使用在前；带关键词则按标题过滤）。 */
export async function fetchSessions(
  keyword = '',
  signal?: AbortSignal,
): Promise<SessionListBody> {
  return apiRequest<SessionListBody>(sessionListUrl(keyword), { signal })
}

/** 新建备课会话：标题（可留空）、追问粒度与参考资料一并交给服务端保存。 */
export async function createSession(
  input: SessionCreateRequest = {},
  signal?: AbortSignal,
): Promise<SessionSummary> {
  return apiRequest<SessionSummary>(sessionsUrl, { method: 'POST', body: input, signal })
}

/** 会话历史：会话 + 按序号排好的完整消息（换设备回看靠它，不靠浏览器缓存）。 */
export async function fetchSessionHistory(
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionHistoryBody> {
  return apiRequest<SessionHistoryBody>(sessionDetailUrl(sessionId), { signal })
}

/** 改会话设置：重命名（title）、追问粒度、参考资料（只改传入的字段）。 */
export async function updateSession(
  sessionId: string,
  patch: SessionUpdateRequest,
  signal?: AbortSignal,
): Promise<SessionSummary> {
  return apiRequest<SessionSummary>(sessionDetailUrl(sessionId), {
    method: 'PATCH',
    body: patch,
    signal,
  })
}

/** 删除备课会话（连同它的全部消息）。 */
export async function deleteSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<DeleteSessionApiV1SessionsSessionIdDeleteResponse> {
  return apiRequest<DeleteSessionApiV1SessionsSessionIdDeleteResponse>(sessionDetailUrl(sessionId), {
    method: 'DELETE',
    signal,
  })
}

/**
 * 一轮备课：只把**本轮原话**交给服务端，澄清还是生成由 `core` 状态机判定；
 * 追问粒度与参考资料以会话上的设置为准（改它们走 `updateSession`）。
 */
export async function sendTurn(
  sessionId: string,
  utterance: string,
  signal?: AbortSignal,
): Promise<ChatApiV1ChatPostResponse> {
  const body: ChatRequest = {
    session_id: sessionId,
    messages: [{ role: 'user', content: utterance }],
  }
  return apiRequest<ChatApiV1ChatPostResponse>(chatUrl, { method: 'POST', body, signal })
}

/** 上传一份教学资料并标记为参考资料，返回它在知识库里的记录（读不出编号时返回 null）。 */
export async function uploadKnowledgeDocument(
  file: File,
  signal?: AbortSignal,
): Promise<KnowledgeDocument | null> {
  const form = new FormData()
  form.set('file', file)
  // 会话内上传的资料就是本次备课的参考资料：标记 + 随后绑进会话（见 useAttachReference）
  form.set('is_reference', 'true')
  const payload = await apiRequest<unknown>(documentUploadUrl, {
    method: 'POST',
    body: form,
    signal,
  })
  return readKnowledgeDocument(payload)
}

/** 知识库里全部教学资料（勾参考资料时读；形状由 `narrowing.ts` 收窄）。 */
export async function fetchKnowledgeDocuments(signal?: AbortSignal): Promise<KnowledgeDocument[]> {
  return readKnowledgeDocuments(await apiRequest<unknown>(documentsUrl, { signal }))
}

/** 把一份资料并入会话的参考资料：服务端保存整份清单，已在清单里的不重复加。 */
export function withReference(docIds: readonly string[], docId: string): string[] {
  return docIds.includes(docId) ? [...docIds] : [...docIds, docId]
}

/** 设定会话的参考资料（整份清单）。 */
export async function setSessionReferences(
  sessionId: string,
  docIds: readonly string[],
  signal?: AbortSignal,
): Promise<SessionSummary> {
  return updateSession(sessionId, { reference_doc_ids: [...docIds] }, signal)
}

// ---- query key ----

export const lessonPrepKeys = {
  all: ['lesson-prep'] as const,
  /** 会话列表的公共前缀：任何一次会话增删改都要让它作废。 */
  sessionLists: () => [...lessonPrepKeys.all, 'sessions'] as const,
  sessionList: (keyword: string) => [...lessonPrepKeys.sessionLists(), keyword] as const,
  sessionHistories: () => [...lessonPrepKeys.all, 'session'] as const,
  sessionHistory: (sessionId: string) => [...lessonPrepKeys.sessionHistories(), sessionId] as const,
  knowledgeDocuments: () => [...lessonPrepKeys.all, 'knowledge-documents'] as const,
}

// ---- 缓存改写（纯函数，便于单独核对）----

/**
 * 一轮对话的乐观追加：先把教师这句话写进缓存，教师看到自己的话立刻出现在轴上；
 * 请求失败时回滚成服务端事实（消息与序号始终以服务端为准）。
 */
export function appendTeacherMessage(
  history: SessionHistoryBody,
  content: string,
  optimisticId: string,
): SessionHistoryBody {
  const nextSeq = history.messages.reduce((max, message) => Math.max(max, message.seq), 0) + 1
  return {
    session: { ...history.session, message_count: history.session.message_count + 1 },
    messages: [
      ...history.messages,
      {
        id: optimisticId,
        seq: nextSeq,
        role: 'user',
        content,
        kind: null,
        artifacts: null,
        created_at: new Date().toISOString(),
      },
    ],
  }
}

/** 服务端返回的新会话摘要替换缓存里的那一份（消息不动）。 */
function replaceSessionSummary(
  history: SessionHistoryBody | undefined,
  session: SessionSummary,
): SessionHistoryBody | undefined {
  return history ? { ...history, session } : history
}

// ---- hooks 层 ----

/**
 * 会话列表。挂载即重取：服务端才是事实源，别处新建/改名的会话进来就能看到；
 * 检索关键词变化时保留上一批数据（`keepPreviousData`），列表不会闪成空白。
 */
export function useSessions(keyword = '') {
  return useQuery({
    queryKey: lessonPrepKeys.sessionList(keyword),
    queryFn: ({ signal }) => fetchSessions(keyword, signal),
    placeholderData: keepPreviousData,
    refetchOnMount: 'always',
  })
}

/** 会话历史。404 = 这次备课没了（被删），要立刻呈现，不靠重试掩盖。 */
export function useSessionHistory(sessionId: string | null) {
  return useQuery({
    queryKey: lessonPrepKeys.sessionHistory(sessionId ?? ''),
    queryFn: ({ signal }) => fetchSessionHistory(sessionId ?? '', signal),
    enabled: Boolean(sessionId),
    retry: false,
  })
}

/** 知识库资料列表（发起会话与改会话设置时勾参考资料用）。 */
export function useKnowledgeDocuments() {
  return useQuery({
    queryKey: lessonPrepKeys.knowledgeDocuments(),
    queryFn: ({ signal }) => fetchKnowledgeDocuments(signal),
  })
}

/** 新建备课会话。 */
export function useCreateSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: SessionCreateRequest) => createSession(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: lessonPrepKeys.sessionLists() })
    },
  })
}

/** 改会话设置（重命名 / 追问粒度 / 参考资料）：只改传入字段，改完立即影响后续对话。 */
export function useUpdateSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sessionId, patch }: { sessionId: string; patch: SessionUpdateRequest }) =>
      updateSession(sessionId, patch),
    onSuccess: (session) => {
      queryClient.setQueryData(
        lessonPrepKeys.sessionHistory(session.id),
        (previous: SessionHistoryBody | undefined) => replaceSessionSummary(previous, session),
      )
      // 最近使用时间变了 → 列表顺序与元信息都要跟上
      void queryClient.invalidateQueries({ queryKey: lessonPrepKeys.sessionLists() })
    },
  })
}

/** 删除备课会话：连同它的消息一起，从列表与缓存里都清掉。 */
export function useDeleteSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => deleteSession(sessionId),
    onSuccess: (result) => {
      queryClient.removeQueries({ queryKey: lessonPrepKeys.sessionHistory(result.id) })
      void queryClient.invalidateQueries({ queryKey: lessonPrepKeys.sessionLists() })
    },
  })
}

/**
 * 会话内一轮对话：失败时回滚乐观改写，成功与否都以服务端返回为准重新拉一遍
 * （会话标题、消息序号、列表顺序都会变）。
 */
export function useSendTurn(sessionId: string) {
  const queryClient = useQueryClient()
  const historyKey = lessonPrepKeys.sessionHistory(sessionId)
  return useMutation({
    mutationFn: (utterance: string) => sendTurn(sessionId, utterance),
    onMutate: async (utterance) => {
      await queryClient.cancelQueries({ queryKey: historyKey })
      const previous = queryClient.getQueryData<SessionHistoryBody>(historyKey)
      if (previous) {
        queryClient.setQueryData(
          historyKey,
          appendTeacherMessage(previous, utterance, `optimistic-${Date.now()}`),
        )
      }
      return { previous }
    },
    onError: (_error, _utterance, context) => {
      if (context?.previous) queryClient.setQueryData(historyKey, context.previous)
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: historyKey })
      void queryClient.invalidateQueries({ queryKey: lessonPrepKeys.sessionLists() })
      // 这一轮可能产出了新的生成物版本：对话旁的并排预览与生成物区用的是同一份版本数据
      // （`artifactKeys.sessionArtifacts`），一次失效两处一起跟上。
      void queryClient.invalidateQueries({ queryKey: artifactKeys.sessionArtifacts() })
      void queryClient.invalidateQueries({ queryKey: artifactKeys.versions() })
    },
  })
}

/**
 * 会话内上传文件：上传进知识库（标记为参考资料）→ 立刻并入本次备课的参考资料。
 * 两步都成功才算成功；上传成功但并入失败会明确报错（资料已在知识库，重试即可）。
 */
export function useAttachReference(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, currentIds }: { file: File; currentIds: readonly string[] }) => {
      const document = await uploadKnowledgeDocument(file)
      if (!document) {
        throw new Error('资料已上传，但没拿到它的编号，没能并入本次备课的参考资料')
      }
      const updated = await setSessionReferences(sessionId, withReference(currentIds, document.id))
      return { document, updated }
    },
    onSuccess: ({ updated }) => {
      queryClient.setQueryData(
        lessonPrepKeys.sessionHistory(sessionId),
        (previous: SessionHistoryBody | undefined) => replaceSessionSummary(previous, updated),
      )
      // 新资料也要出现在勾选清单里
      void queryClient.invalidateQueries({ queryKey: lessonPrepKeys.knowledgeDocuments() })
      void queryClient.invalidateQueries({ queryKey: lessonPrepKeys.sessionLists() })
    },
  })
}
