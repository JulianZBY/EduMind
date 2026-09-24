/**
 * 冲突审核区的服务端状态（TanStack Query）。
 * 约定：query key 以 `conflictKeys.all` 打头，hooks 只住本文件。
 *
 * 两个端点（类型与路径都取自生成的 schema，不手抄）：
 * - `GET /conflicts?category=`：某一类别的冲突队列（含已裁决的，终态由服务端给）；
 * - `POST /conflicts/{conflict_id}/review`：裁决一条待审冲突。
 *
 * 队列更新的口径（验收项）：裁决成功后**使整类队列作废重取**，不自己推算终态——
 * 「并存」与「已接受」的呈现不同，本地乐观更新容易把两者画成一样。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest } from '../../api/client'
import type {
  ListConflictsApiV1ConflictsGetData,
  ListConflictsApiV1ConflictsGetResponse,
  ReviewConflictApiV1ConflictsConflictIdReviewPostData,
  ReviewConflictApiV1ConflictsConflictIdReviewPostResponse,
} from '../../api/generated'
import type { ConflictCategory, ReviewAction } from './actions'

export const CONFLICTS_URL: ListConflictsApiV1ConflictsGetData['url'] = '/api/v1/conflicts'
export const REVIEW_URL: ReviewConflictApiV1ConflictsConflictIdReviewPostData['url'] =
  '/api/v1/conflicts/{conflict_id}/review'

export const conflictKeys = {
  all: ['conflicts'] as const,
  queue: (category: ConflictCategory) => [...conflictKeys.all, 'queue', category] as const,
}

/** 某一类别的冲突队列（按类别分区呈现）。 */
export function useConflictQueue(category: ConflictCategory) {
  return useQuery({
    queryKey: conflictKeys.queue(category),
    queryFn: ({ signal }) =>
      apiRequest<ListConflictsApiV1ConflictsGetResponse>(
        `${CONFLICTS_URL}?${new URLSearchParams({ category })}`,
        { signal },
      ),
  })
}

export interface ReviewVariables {
  conflictId: string
  action: ReviewAction
  /** 仅「编辑修正后入库」需要：教师改对后的正文。 */
  revisedContent?: string
}

/** 裁决一条待审冲突；成功即让队列作废，队列随之显示服务端给的终态。 */
export function useReviewConflict() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ conflictId, action, revisedContent }: ReviewVariables) =>
      apiRequest<ReviewConflictApiV1ConflictsConflictIdReviewPostResponse>(
        REVIEW_URL.replace('{conflict_id}', encodeURIComponent(conflictId)),
        {
          method: 'POST',
          body:
            revisedContent === undefined
              ? { action }
              : { action, revised_content: revisedContent },
        },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: conflictKeys.all })
    },
  })
}

/** 失败详情 → 面向教师的一句话（接口的 status 语义见 `docs/api/conflicts.md`）。 */
export function conflictErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return '这条冲突已经不在队列里了，刷新后再看。'
    if (error.status === 409) return '这条冲突已经裁决过，不能重复提交。'
    if (error.status === 422) return '这个动作不适用于这类冲突，或者缺少需要的内容。'
  }
  return '后端没有回应或返回了错误，稍后重试一次。'
}
