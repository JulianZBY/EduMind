/**
 * 某个类别的冲突队列：取数据 → 三态（加载 / 失败 / 空）→ 逐条裁决卡。
 *
 * 裁决成功后由 `useReviewConflict` 让整类队列作废重取，卡片随之显示服务端给的终态
 * （「并存」与「已接受」的呈现不同，故不做乐观更新）。
 */
import type { ConflictItem } from '../../api/generated'
import { FlatLoading } from '../../components/graph'
import { Button, EmptyState } from '../../components/ui'
import { useToast } from '../../components/ui/useToast'
import { ConflictCard } from './ConflictCard'
import { conflictErrorMessage, useConflictQueue, useReviewConflict } from './queries'
import { statusLabel } from './actions'
import type { ConflictCategory, ReviewAction } from './actions'

export interface ConflictQueuePanelProps {
  category: ConflictCategory
  emptyTitle: string
  emptyDescription: string
  /** 这一类别的检测状态说明（文案纪律：不承诺尚未实现的检测）。 */
  note: string
}

export function ConflictQueuePanel({
  category,
  emptyTitle,
  emptyDescription,
  note,
}: ConflictQueuePanelProps) {
  const queue = useConflictQueue(category)
  const review = useReviewConflict()
  const { toast } = useToast()

  function decide(conflict: ConflictItem, action: ReviewAction, revisedContent?: string) {
    review.mutate(
      { conflictId: conflict.id, action, revisedContent },
      {
        onSuccess: (result) => {
          toast({
            title: `已记下裁决：${statusLabel(result.status)}`,
            description: `这条${result.category}按「${result.action}」处置，队列已更新。`,
            tone: 'default',
          })
        },
        onError: (error) => {
          toast({
            title: '裁决没有生效',
            description: conflictErrorMessage(error),
            tone: 'accent',
          })
        },
      },
    )
  }

  if (queue.isError) {
    return (
      <div
        role="status"
        className="m-3 rounded-none border-2 border-[#ff3366] px-3 py-2 text-sm text-black"
      >
        <p className="font-bold">冲突队列没读出来</p>
        <p className="mt-1 text-xs text-black/60">
          「{category}」队列接口暂时不可用，可以重试一次。
        </p>
        <Button size="sm" className="mt-2" onClick={() => void queue.refetch()}>
          重试
        </Button>
      </div>
    )
  }

  if (queue.isPending) {
    return <FlatLoading text={`正在取「${category}」队列…`} />
  }

  const conflicts = queue.data.conflicts
  const pendingCount = conflicts.filter((conflict) => conflict.status === '待审').length

  return (
    <div className="flex flex-col gap-3 p-3">
      <p className="rounded-none border-2 border-black px-3 py-2 text-xs leading-5 text-black/60">
        {note}
      </p>

      {conflicts.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyDescription} />
      ) : (
        <>
          <p className="text-xs text-black/60">
            {pendingCount} 条待审 · 共 {conflicts.length} 条（裁决过的保留在列表里，终态可复核）
          </p>
          {conflicts.map((conflict) => (
            <ConflictCard
              key={conflict.id}
              conflict={conflict}
              pending={review.isPending && review.variables?.conflictId === conflict.id}
              onDecide={(action, revisedContent) => decide(conflict, action, revisedContent)}
            />
          ))}
        </>
      )}
    </div>
  )
}
