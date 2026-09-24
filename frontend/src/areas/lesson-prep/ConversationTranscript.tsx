/**
 * 对话轴：把会话消息按序号铺开，并正确区分**澄清回复**与**生成回复**两种形态
 * （CONTEXT.md：澄清回复的内容是追问、不给生成物；生成回复才带生成物与溯源）。
 *
 * 除历史消息外，还承载本轮对话的过程态：进行中（请求未回）与失败（可重试）。
 * 纯渲染组件：数据由 `ConversationAxis` 传入，方便在没有浏览器时直接渲染核对。
 */
import { useEffect, useRef } from 'react'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/EmptyState'
import { formatTimestamp } from './format'
import { GeneratedResult } from './GeneratedResult'
import { readReplyForm } from './narrowing'
import type { SessionMessage } from './queries'

/** 回答这条消息的时间与序号（工作台密度的小字）。 */
function MessageMeta({ message }: { message: SessionMessage }) {
  return (
    <span className="text-xs text-black/60">
      第 {message.seq} 条 · {formatTimestamp(message.created_at)}
    </span>
  )
}

function TeacherMessage({ message }: { message: SessionMessage }) {
  return (
    <article className="border-b-2 border-black px-3 py-3">
      <header className="mb-1 flex flex-wrap items-baseline gap-2">
        <span className="text-xs font-bold">教师</span>
        <MessageMeta message={message} />
      </header>
      <p className="text-sm leading-6 break-words whitespace-pre-wrap">{message.content}</p>
    </article>
  )
}

function AssistantMessage({ message }: { message: SessionMessage }) {
  const form = readReplyForm(message.kind)
  const generated = form === '生成回复'

  return (
    <article className="border-b-2 border-black px-3 py-3">
      <header className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-xs font-bold">助手</span>
        {/* 两种形态互斥（CONTEXT.md）：实心标签 = 生成回复，描边标签 = 澄清回复 */}
        {form ? <Badge tone={generated ? 'solid' : 'outline'}>{form}</Badge> : null}
        <MessageMeta message={message} />
      </header>
      <div className="rounded-none border-2 border-black">
        <p className="px-3 py-2 text-sm leading-6 break-words whitespace-pre-wrap">
          {message.content}
        </p>
        {generated ? <GeneratedResult artifacts={message.artifacts} /> : null}
        {form === '澄清回复' ? (
          <p className="border-t-2 border-black px-3 py-2 text-xs leading-5 text-black/60">
            这是追问，还没有生成物：补上缺的信息，或点「跳过追问，直接生成」让助手出结果。
          </p>
        ) : null}
      </div>
    </article>
  )
}

/** 一行消息：教师说的与助手说的分开渲染（未知 role 当作助手说的，历史不丢行）。 */
export function TranscriptMessage({ message }: { message: SessionMessage }) {
  return message.role === 'user' ? (
    <TeacherMessage message={message} />
  ) : (
    <AssistantMessage message={message} />
  )
}

function PendingTurn() {
  return (
    <article className="border-b-2 border-black px-3 py-3" role="status">
      <header className="mb-1 flex flex-wrap items-baseline gap-2">
        <span className="text-xs font-bold">助手</span>
        <span className="text-xs text-black/60">正在备课…</span>
      </header>
      <div className="h-1.5 w-full rounded-none border-2 border-black">
        <div className="h-full w-1/3 bg-black" />
      </div>
      <p className="mt-2 text-xs leading-5 text-black/60">
        正在按累积需求判断还缺什么：需要就继续追问，信息够用就直接出生成物。
      </p>
    </article>
  )
}

function FailedTurn({ utterance, onRetry }: { utterance: string; onRetry: () => void }) {
  return (
    <article className="border-b-2 border-black px-3 py-3" role="alert">
      <p className="text-xs font-bold text-[#ff3366]">这一轮没跑完</p>
      <p className="mt-1 text-xs leading-5">
        已入库的对话不会丢。可以原样重试这一轮；重试不会丢掉前面的内容。
      </p>
      <p className="mt-2 text-sm break-words whitespace-pre-wrap">
        <span className="font-bold">重试内容：</span>
        {utterance}
      </p>
      <Button size="sm" className="mt-2" onClick={onRetry}>
        重试这一轮
      </Button>
    </article>
  )
}

export interface ConversationTranscriptProps {
  messages: readonly SessionMessage[]
  /** 一轮对话进行中（请求未回）。 */
  isTurnPending: boolean
  /** 上一轮失败时教师说的那句原话；非空才显示失败行与重试。 */
  failedUtterance: string | null
  onRetry: () => void
}

export function ConversationTranscript({
  messages,
  isTurnPending,
  failedUtterance,
  onRetry,
}: ConversationTranscriptProps) {
  const failed = failedUtterance ?? null
  const end = useRef<HTMLDivElement>(null)
  const empty = messages.length === 0 && !isTurnPending && failed === null

  // 新消息、进行中、失败三种变化都把视图跟进到底部（对话轴看的是最新一轮）
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, isTurnPending, failed])

  if (empty) {
    return (
      <EmptyState
        title="开始这次备课"
        description="说说这节课：主题、学段、时长。信息不够时助手会追问，追问粒度可以随时调；信息够用就直接出生成物。"
      />
    )
  }

  return (
    <>
      {messages.map((message) => (
        <TranscriptMessage key={message.id} message={message} />
      ))}
      {isTurnPending ? <PendingTurn /> : null}
      {!isTurnPending && failed !== null ? (
        <FailedTurn utterance={failed} onRetry={onRetry} />
      ) : null}
      <div ref={end} />
    </>
  )
}
