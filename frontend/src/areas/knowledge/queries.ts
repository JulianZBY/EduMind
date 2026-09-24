/**
 * 知识库区的服务端状态（TanStack Query）。
 *
 * 纪律（ADR-0005 / 票 04）：
 * - URL 常量取自生成的 schema，不手拼路径、不手抄接口类型；
 * - 解析状态跟进靠**轮询策略**：还有资料在「处理中」就保持轮询，全部落终态即停
 *   ——教师不需要点「刷新」（CONTEXT.md 第 4 节状态口径）；
 * - 缓存复用：`staleTime` 内重复进入知识库直接命中缓存，不重新请求。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest } from '../../api/client'
import type {
  DocumentDetail,
  DocumentListResponse,
  DocumentView,
  GetDocumentApiV1DocumentsDocumentIdGetData,
  ListDocumentsApiV1DocumentsGetData,
  ReferenceRequest,
  SetReferenceApiV1DocumentsDocumentIdReferencePatchData,
  UploadDocumentApiV1DocumentsUploadPostData,
} from '../../api/generated'
import { hasProcessing, isProcessing } from './status'

/** URL 一律从生成的 schema 取（`npm run gen:api`），改后端路径时这里会编译报错。 */
const documentsUrl: ListDocumentsApiV1DocumentsGetData['url'] = '/api/v1/documents'
const uploadUrl: UploadDocumentApiV1DocumentsUploadPostData['url'] = '/api/v1/documents/upload'
const detailUrlTemplate: GetDocumentApiV1DocumentsDocumentIdGetData['url'] =
  '/api/v1/documents/{document_id}'
const referenceUrlTemplate: SetReferenceApiV1DocumentsDocumentIdReferencePatchData['url'] =
  '/api/v1/documents/{document_id}/reference'

/** 把生成 URL 模板里的路径参数换成实际 id（编码后拼，仍然不手写路径）。 */
function documentUrl(template: string, documentId: string): string {
  return template.replace('{document_id}', encodeURIComponent(documentId))
}

/** 轮询间隔：还在解析时的跟进节奏；全部落终态即停。 */
const POLL_INTERVAL_MS = 1500
const STALE_TIME_MS = 30_000

export const knowledgeKeys = {
  all: ['knowledge'] as const,
  list: () => [...knowledgeKeys.all, 'list'] as const,
  detail: (documentId: string) => [...knowledgeKeys.all, 'detail', documentId] as const,
}

/** 接口错误翻成教师能读的一句话（界面上不出现 4xx/5xx 这类工程术语）。 */
export function documentErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return '这份资料已不存在，请回到资料列表重新选择。'
    if (error.status === 422) return '请求内容不符合要求，请换一个文件再试。'
  }
  return '操作没有成功，请稍后重试。'
}

/** 教学资料列表：有「处理中」的资料就保持轮询，全部到终态自动停。 */
export function useDocuments() {
  return useQuery({
    queryKey: knowledgeKeys.list(),
    queryFn: ({ signal }) => apiRequest<DocumentListResponse>(documentsUrl, { signal }),
    refetchInterval: (query) =>
      hasProcessing(query.state.data?.documents) ? POLL_INTERVAL_MS : false,
    staleTime: STALE_TIME_MS,
  })
}

/** 一份教学资料的详情：同样跟着解析状态轮询到终态。 */
export function useDocument(documentId: string | undefined) {
  return useQuery({
    queryKey: knowledgeKeys.detail(documentId ?? ''),
    enabled: Boolean(documentId),
    queryFn: ({ signal }) =>
      apiRequest<DocumentDetail>(documentUrl(detailUrlTemplate, documentId ?? ''), { signal }),
    refetchInterval: (query) =>
      query.state.data && isProcessing(query.state.data.status) ? POLL_INTERVAL_MS : false,
    staleTime: STALE_TIME_MS,
  })
}

/**
 * 上传教学资料：成功后让本区缓存失效——列表立刻带上新资料（`处理中`），
 * 随后由列表自身的轮询接手跟进到终态。
 */
export function useUploadDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { file: File; isReference: boolean }) => {
      const body = new FormData()
      body.append('file', input.file)
      body.append('is_reference', String(input.isReference))
      return apiRequest<DocumentView>(uploadUrl, { method: 'POST', body })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.all })
    },
  })
}

export interface ReferenceInput {
  documentId: string
  isReference: boolean
}

/** 乐观改写前的缓存快照：接口失败时按它回滚。 */
export interface ReferenceSnapshot {
  list: DocumentListResponse | undefined
  detail: DocumentDetail | undefined
}

/**
 * 「即时生效」的那一步：不等接口回话，先把列表与详情缓存里的标记改成目标值。
 * 只改已存在的缓存，不会凭白创建空缓存（缓存没预热就不动）。
 */
export function applyReferenceOptimistically(
  queryClient: QueryClient,
  input: ReferenceInput,
): ReferenceSnapshot {
  const list = queryClient.getQueryData<DocumentListResponse>(knowledgeKeys.list())
  const detail = queryClient.getQueryData<DocumentDetail>(knowledgeKeys.detail(input.documentId))
  if (list) {
    queryClient.setQueryData<DocumentListResponse>(knowledgeKeys.list(), {
      documents: list.documents.map((document) =>
        document.id === input.documentId
          ? { ...document, is_reference: input.isReference }
          : document,
      ),
    })
  }
  if (detail) {
    queryClient.setQueryData<DocumentDetail>(knowledgeKeys.detail(input.documentId), {
      ...detail,
      is_reference: input.isReference,
    })
  }
  return { list, detail }
}

/** 接口失败：把两个缓存都退回切换前的快照。 */
export function rollbackReference(queryClient: QueryClient, snapshot: ReferenceSnapshot): void {
  if (snapshot.list) queryClient.setQueryData(knowledgeKeys.list(), snapshot.list)
  if (snapshot.detail) {
    queryClient.setQueryData(knowledgeKeys.detail(snapshot.detail.id), snapshot.detail)
  }
}

/**
 * 切换参考资料标记（即时生效）：先按目标值改写缓存里的列表与详情，
 * 再等接口回话；失败回滚到切换前的快照（并在界面提示）。
 */
export function useSetDocumentReference() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: ReferenceInput) =>
      apiRequest<DocumentView>(documentUrl(referenceUrlTemplate, input.documentId), {
        method: 'PATCH',
        body: { is_reference: input.isReference } satisfies ReferenceRequest,
      }),
    onMutate: async (input) => {
      await queryClient.cancelQueries({ queryKey: knowledgeKeys.all })
      return applyReferenceOptimistically(queryClient, input)
    },
    onError: (_error, _input, snapshot) => {
      if (snapshot) rollbackReference(queryClient, snapshot)
    },
    onSettled: (_data, _error, input) => {
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.list() })
      queryClient.invalidateQueries({ queryKey: knowledgeKeys.detail(input.documentId) })
    },
  })
}
