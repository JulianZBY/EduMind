/**
 * 题库区的服务端状态（TanStack Query）。
 * 约定：query key 以 `questionKeys.all` 打头，hooks 只住本文件。
 *
 * 请求地址与查询参数类型全部取自生成的 schema（`src/api/generated`，ADR-0005 禁止手抄）；
 * 题目列表按考查知识点筛选 + 分页，题目详情按 id 取单道题。
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import type { ApiResponseBody } from '../../api/client'
import type {
  GetQuestionApiV1QuestionsQuestionIdGetData,
  GetQuestionApiV1QuestionsQuestionIdGetResponses,
  ListQuestionsApiV1QuestionsGetData,
  ListQuestionsApiV1QuestionsGetResponses,
} from '../../api/generated'

/** 列表页容量：工作台密度下一屏尽量多信息，同时不超过接口上限 100。 */
export const PAGE_SIZE = 20

const listUrl: ListQuestionsApiV1QuestionsGetData['url'] = '/api/v1/questions'
const detailUrlTemplate: GetQuestionApiV1QuestionsQuestionIdGetData['url'] =
  '/api/v1/questions/{question_id}'

/** 列表查询条件（`knowledge_point` 为空 = 全部题目）。 */
export type QuestionListQuery = NonNullable<ListQuestionsApiV1QuestionsGetData['query']>

/** 列表响应体与其中的列表行类型：不另抄一份形状，直接从生成的响应类型里取。 */
export type QuestionListBody = ApiResponseBody<ListQuestionsApiV1QuestionsGetResponses, 200>
export type QuestionSummary = QuestionListBody['items'][number]
export type QuestionKnowledgePoint = QuestionSummary['knowledge_points'][number]
export type QuestionDetailBody = ApiResponseBody<
  GetQuestionApiV1QuestionsQuestionIdGetResponses,
  200
>

export const questionKeys = {
  all: ['question-bank'] as const,
  list: (query: QuestionListQuery) => [...questionKeys.all, 'list', query] as const,
  detail: (questionId: string) => [...questionKeys.all, 'detail', questionId] as const,
}

/** 拼列表地址：筛选与分页都走查询参数，与 schema 里声明的参数名一致。 */
export function buildQuestionListUrl(query: QuestionListQuery): string {
  const params = new URLSearchParams()
  if (query.knowledge_point) params.set('knowledge_point', query.knowledge_point)
  params.set('limit', String(query.limit ?? PAGE_SIZE))
  params.set('offset', String(query.offset ?? 0))
  return `${listUrl}?${params.toString()}`
}

/**
 * 题目列表（按考查知识点筛选 + 分页）。
 * 挂载即重取：试卷刚入库的题目要能立刻出现在列表里，不能被缓存挡住；
 * 翻页时保留上一页数据（`keepPreviousData`），列表不会闪成空白。
 */
export function useQuestions(query: QuestionListQuery) {
  return useQuery({
    queryKey: questionKeys.list(query),
    queryFn: ({ signal }) => apiRequest<QuestionListBody>(buildQuestionListUrl(query), { signal }),
    refetchOnMount: 'always',
    placeholderData: keepPreviousData,
  })
}

/** 题目详情：题型 / 答案 / 来源 / 考查知识点。失败不重试，404 要立刻呈现为「题目不存在」。 */
export function useQuestion(questionId: string | null) {
  return useQuery({
    queryKey: questionKeys.detail(questionId ?? ''),
    queryFn: ({ signal }) =>
      apiRequest<QuestionDetailBody>(
        detailUrlTemplate.replace('{question_id}', encodeURIComponent(questionId ?? '')),
        { signal },
      ),
    enabled: Boolean(questionId),
    retry: false,
    refetchOnMount: 'always',
  })
}
