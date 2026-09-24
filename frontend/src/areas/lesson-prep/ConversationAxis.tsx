/**
 * 主区 = 对话主轴：会话标题与设置条（追问粒度三档、参考资料）、对话轴、输入区。
 *
 * 三段结构是有意的：标题与设置固定在顶、对话可滚动、输入固定在底（长对话里输入框不该被滚走）。
 * 全部数据来自服务端（TanStack Query）：刷新、换设备进来都是同一条历史。
 * 生成物的版本中心不在这里（票 08）；这里只给本轮结果的最小入口，见 `GeneratedResult`。
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../api/client'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { EmptyState } from '../../components/ui/EmptyState'
import { useToast } from '../../components/ui/useToast'
import { ConversationComposer } from './ConversationComposer'
import { ConversationTranscript } from './ConversationTranscript'
import { GranularityPicker } from './GranularityPicker'
import { ReferencePicker } from './ReferencePicker'
import type { Granularity, SessionHistoryBody } from './queries'
import { useAttachReference, useSendTurn, useSessionHistory, useUpdateSession } from './queries'
import { LESSON_PREP_PATH } from './routes'

/** 上传失败的说法：后端明确拒绝与「上传成功但没算作参考资料」分开讲，教师才知道重试有没有意义。 */
function uploadFailureMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) return '这份文件后端没收（格式或大小不合要求），换一份再试。'
    return '上传没成功：后端暂时收不到这份资料，重试即可。'
  }
  if (error instanceof Error && error.message) return error.message
  return '上传没成功：后端暂时收不到这份资料，重试即可。'
}

/** 会话设置条上的一行机器口径（选中对象可读可核对，风格文档第 7 节允许）。 */function SessionMeta({ history }: { history: SessionHistoryBody }) {
  const { session } = history
  return (
    <p className="text-xs text-black/60">
      备课会话 · 消息 {session.message_count} 条 · 参考资料 {session.reference_doc_ids.length} 份 ·
      会话 {session.id}
    </p>
  )
}

function AxisPanel({ children }: { children: ReactNode }) {
  return <section className="flex min-h-0 w-full flex-1 flex-col">{children}</section>
}

/** 读取历史时的面板（刷新进入会话的第一眼）。 */
function HistoryLoading({ sessionId }: { sessionId: string }) {
  return (
    <AxisPanel>
      <header className="flex flex-wrap items-baseline gap-2 border-b-2 border-black px-3 py-2">
        <h1 className="text-sm font-bold">备课会话</h1>
        <p className="text-xs text-black/60">会话 {sessionId}</p>
      </header>
      <div className="px-3 py-3" role="status">
        <p className="text-xs">正在读取这次备课的历史…</p>
        <div className="mt-2 h-1.5 w-full rounded-none border-2 border-black">
          <div className="h-full w-1/3 bg-black" />
        </div>
      </div>
    </AxisPanel>
  )
}

/** 历史取不到：404（会话被删）与其它失败分开说法，各自给出路。 */
function HistoryUnavailable({
  sessionId,
  notFound,
  onRetry,
}: {
  sessionId: string
  notFound: boolean
  onRetry: () => void
}) {
  if (notFound) {
    return (
      <EmptyState
        title="备课会话不存在"
        description="这次备课可能已被删除。回到会话列表重新选一条，或新建一次备课。"
        meta={`备课会话：${sessionId}`}
        action={
          <>
            <Button asChild size="sm">
              <Link to={LESSON_PREP_PATH}>返回会话列表</Link>
            </Button>
            <Button asChild size="sm">
              <Link to={{ pathname: LESSON_PREP_PATH, search: '?new=1' }}>新建备课会话</Link>
            </Button>
          </>
        }
      />
    )
  }
  return (
    <EmptyState
      title="这次备课取不到"
      description="后端暂时取不到会话数据。已入库的历史不会丢，确认后端已启动后可重试。"
      meta={`备课会话：${sessionId}`}
      action={
        <Button size="sm" onClick={onRetry}>
          重试
        </Button>
      }
    />
  )
}

/** 会话设置的参考资料弹层：只在打开时挂载，初值就是服务端上的那份清单。 */
function ReferencesDialog({
  sessionId,
  initialIds,
  onClose,
}: {
  sessionId: string
  initialIds: readonly string[]
  onClose: () => void
}) {
  const { toast } = useToast()
  const update = useUpdateSession()
  const [ids, setIds] = useState<string[]>([...initialIds])
  const [error, setError] = useState<string | null>(null)

  const save = () => {
    setError(null)
    update.mutate(
      { sessionId, patch: { reference_doc_ids: ids } },
      {
        onSuccess: () => {
          toast({
            title: '参考资料已更新',
            description:
              ids.length > 0 ? `后续对话按这 ${ids.length} 份资料加权。` : '后续对话不再按资料加权。',
            tone: 'default',
          })
          onClose()
        },
        onError: () => setError('没保存上：后端暂时改不了这次备课的设置。重试即可，勾选还在。'),
      },
    )
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="本次备课的参考资料"
      description="改完立即影响后续对话（检索加权与生成物溯源）。"
      footer={
        <>
          <Button size="sm" onClick={onClose}>
            取消
          </Button>
          <Button variant="accent" size="sm" disabled={update.isPending} onClick={save}>
            {update.isPending ? '正在保存…' : '保存参考资料'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <ReferencePicker selectedIds={ids} onChange={setIds} />
        {error ? <p className="text-xs font-bold text-[#ff3366]">{error}</p> : null}
      </div>
    </Dialog>
  )
}

export function ConversationAxis({ sessionId }: { sessionId: string }) {
  const { toast } = useToast()
  const history = useSessionHistory(sessionId)
  const send = useSendTurn(sessionId)
  const update = useUpdateSession()
  const attach = useAttachReference(sessionId)
  const [failedUtterance, setFailedUtterance] = useState<string | null>(null)
  const [referencesOpen, setReferencesOpen] = useState(false)

  const runTurn = (utterance: string) => {
    setFailedUtterance(null)
    send.mutate(utterance, {
      onError: () => setFailedUtterance(utterance),
    })
  }

  if (history.isPending) return <HistoryLoading sessionId={sessionId} />

  if (history.isError) {
    return (
      <HistoryUnavailable
        sessionId={sessionId}
        notFound={history.error instanceof ApiError && history.error.status === 404}
        onRetry={() => void history.refetch()}
      />
    )
  }

  const { session, messages } = history.data

  const changeGranularity = (granularity: Granularity) => {
    update.mutate(
      { sessionId, patch: { granularity } },
      {
        onSuccess: (updated) => {
          toast({
            title: `追问粒度已切到${updated.granularity}`,
            description: '后续追问按这一档来；已经问过的轮次不受影响。',
            tone: 'default',
          })
        },
        onError: () => {
          toast({
            title: '没改上追问粒度',
            description: '后端暂时改不了这次备课的设置，重试即可。',
            tone: 'accent',
          })
        },
      },
    )
  }

  const uploadReference = (file: File) => {
    attach.mutate(
      { file, currentIds: session.reference_doc_ids },
      {
        onSuccess: ({ document: uploaded }) => {
          toast({
            title: '已归入本次备课的参考资料',
            description: uploaded?.filename ?? file.name,
            tone: 'default',
          })
        },
      },
    )
  }

  return (
    <AxisPanel>
      <header className="flex flex-wrap items-start justify-between gap-2 border-b-2 border-black px-3 py-2">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-sm font-bold">{session.title}</h1>
          <SessionMeta history={history.data} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <GranularityPicker
            value={session.granularity}
            disabled={update.isPending}
            onChange={changeGranularity}
          />
          <Button size="sm" onClick={() => setReferencesOpen(true)}>
            参考资料 {session.reference_doc_ids.length} 份
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        <ConversationTranscript
          messages={messages}
          isTurnPending={send.isPending}
          failedUtterance={failedUtterance}
          onRetry={() => {
            if (failedUtterance !== null) runTurn(failedUtterance)
          }}
        />
      </div>

      <ConversationComposer
        onSend={runTurn}
        onSkip={runTurn}
        onUpload={uploadReference}
        busy={send.isPending}
        uploading={attach.isPending}
        uploadError={attach.isError ? uploadFailureMessage(attach.error) : null}
      />

      {referencesOpen ? (
        <ReferencesDialog
          sessionId={sessionId}
          initialIds={session.reference_doc_ids}
          onClose={() => setReferencesOpen(false)}
        />
      ) : null}
    </AxisPanel>
  )
}
