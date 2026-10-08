/**
 * 新学科提议的待批队列（票 09，CONTEXT.md「学科清单」）。
 *
 * 上传／联网检索入库时，AI 归类认为清单内学科都不合适会提议新学科（名称 + 理由 +
 * 涉及的知识点），在这里等教师处理。批准是显式动作：批准才入清单并触发相关
 * 「未分类」知识点重新归类；拒绝后提议消亡、知识点留在「未分类」。
 * 批准入口住知识库区，不走冲突审核——那里只裁决矛盾。
 */
import { useState } from 'react'
import type { ProposalView } from '../../api/generated'
import { apiErrorMessage } from '../../api/client'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { useToast } from '../../components/ui/useToast'
import {
  proposalErrorMessage,
  useApproveProposal,
  usePendingProposals,
  useRejectProposal,
} from './queries'

export function ProposalQueue() {
  const [open, setOpen] = useState(false)
  const queue = usePendingProposals()
  const count = queue.data?.proposals.length ?? 0
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        新学科提议{count > 0 ? `（${count}）` : ''}
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="新学科提议"
        description="AI 归类认为清单内学科都不合适时会提议新学科，等你批准或拒绝；批准前它不进学科清单，涉及的知识点留在「未分类」。"
      >
        {open ? <ProposalList /> : null}
      </Dialog>
    </>
  )
}

function ProposalList() {
  const queue = usePendingProposals()
  if (queue.isPending) {
    return <p className="text-black/60">正在读取待批提议…</p>
  }
  if (queue.isError) {
    return (
      <div className="rounded-none border-2 border-[#ff3366] p-3">
        <ErrorNotice error={queue.error} />
        <Button onClick={() => void queue.refetch()}>重试</Button>
      </div>
    )
  }
  if (queue.data.proposals.length === 0) {
    return (
      <p>
        还没有待批的新学科提议。上传资料后，AI
        认为清单内学科都不合适时会在这里提议新学科。
      </p>
    )
  }
  return (
    <ul className="flex flex-col gap-3">
      {queue.data.proposals.map((proposal) => (
        <ProposalCard key={proposal.id} proposal={proposal} />
      ))}
    </ul>
  )
}

function ProposalCard({ proposal }: { proposal: ProposalView }) {
  const approve = useApproveProposal()
  const reject = useRejectProposal()
  const { toast } = useToast()
  const [confirm, setConfirm] = useState(false)
  const busy = approve.isPending || reject.isPending
  return (
    <li className="rounded-none border-2 border-black p-3">
      <p className="font-bold">{proposal.name}</p>
      {proposal.reason ? (
        <p className="mt-1 text-xs leading-5 text-black/60">提议理由：{proposal.reason}</p>
      ) : null}
      {proposal.knowledge_titles.length > 0 ? (
        <>
          <p className="mt-2 text-xs font-bold">
            涉及的知识点（批准后从「未分类」归入新学科）
          </p>
          <ul className="mt-1 flex flex-col gap-1 border-2 border-black p-2">
            {proposal.knowledge_titles.map((title) => (
              <li key={title} className="text-xs leading-5">
                {title}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-2 text-xs leading-5 text-black/60">没有记录到涉及的知识点。</p>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="accent"
          disabled={busy}
          onClick={() =>
            approve.mutate(proposal.id, {
              onSuccess: (result) => {
                toast({
                  title: `已批准：「${proposal.name}」进入学科清单`,
                  description:
                    result.reclassified > 0
                      ? `${result.reclassified} 个知识点从「未分类」归入其中。`
                      : '没有需要重新归类的知识点，学科已可供后续归类使用。',
                  tone: 'default',
                })
              },
              onError: (error) => {
                toast({
                  title: '批准没有生效',
                  description: proposalErrorMessage(error),
                  tone: 'accent',
                })
              },
            })
          }
        >
          {approve.isPending ? '正在批准…' : '批准'}
        </Button>
        <Button
          size="sm"
          disabled={busy}
          onClick={() => {
            reject.reset()
            setConfirm(true)
          }}
        >
          拒绝
        </Button>
      </div>
      <p className="mt-1 text-xs leading-5 text-black/60">
        批准后学科进清单、上述知识点重新归类；拒绝后这条提议消亡，知识点留在「未分类」。
      </p>
      {approve.isError ? <ErrorNotice error={approve.error} /> : null}
      <Dialog
        open={confirm}
        onOpenChange={(value) => {
          if (!reject.isPending) setConfirm(value)
        }}
        title={`拒绝提议「${proposal.name}」？`}
        description="拒绝后这条提议消亡：学科不进清单，涉及的知识点留在「未分类」。"
        footer={
          <>
            <Button disabled={reject.isPending} onClick={() => setConfirm(false)}>
              取消
            </Button>
            <Button
              variant="accent"
              disabled={reject.isPending}
              onClick={() =>
                reject.mutate(proposal.id, {
                  onSuccess: () => {
                    setConfirm(false)
                    toast({
                      title: '已拒绝这条提议',
                      description: '涉及的知识点仍留在「未分类」。',
                      tone: 'default',
                    })
                  },
                })
              }
            >
              {reject.isPending ? '正在拒绝…' : '确认拒绝'}
            </Button>
          </>
        }
      >
        {reject.isError ? (
          <ErrorNotice error={reject.error} />
        ) : (
          <p>下次归类再遇到清单内学科都不合适时，会带新的知识点重新提议。</p>
        )}
      </Dialog>
    </li>
  )
}

function ErrorNotice({ error }: { error: unknown }) {
  return (
    <p
      role="alert"
      className="my-2 rounded-none border-2 border-[#ff3366] p-2 text-black"
    >
      {apiErrorMessage(error, '待批提议没有读出来，请稍后重试。')}
    </p>
  )
}
