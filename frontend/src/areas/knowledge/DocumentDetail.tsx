/**
 * 主区：教学资料详情（工作台密度——贴边分隔线、紧凑行、一屏多信息）。
 *
 * 三块内容：状态与参考资料标记（可切换，即时生效）、解析事实（完成时间 / 分块数 / 待审冲突）、
 * 入库的分块明细（可回溯来源）。资料仍在「处理中」时这里会随轮询自动刷新到终态。
 */
import { Link, useParams } from 'react-router'
import type { DocumentChunk, DocumentDetail as DocumentDetailPayload } from '../../api/generated'
import { EmptyState } from '../../components/ui/EmptyState'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/useToast'
import { cn } from '../../lib/cn'
import { DocumentStatusBadge } from './DocumentStatus'
import { isProcessing, STATUS_NOTE } from './status'
import type { ParseStatus } from './status'
import { documentErrorMessage, useDocument, useSetDocumentReference } from './queries'
import { useKnowledgeUi } from './store'

/** 解析完成时间：本地时区的可读写法；处理中为空。 */
function formatParsedAt(value: string | null | undefined): string {
  if (!value) return '—'
  const at = new Date(value)
  return Number.isNaN(at.getTime()) ? value : at.toLocaleString('zh-CN', { hour12: false })
}

export function DocumentDetail() {
  const { documentId } = useParams<{ documentId: string }>()
  const { data, isPending, isError, refetch } = useDocument(documentId)

  if (isPending) return <p className="px-3 py-12 text-center text-sm text-black/60">正在读取资料详情…</p>

  if (isError || !data) {
    return (
      <EmptyState
        title="这份资料读不出来"
        description="接口没有返回详情：可能资料已不存在，也可能服务暂时不可用。"
        action={
          <Button variant="accent" onClick={() => refetch()}>
            重试
          </Button>
        }
      />
    )
  }

  return (
    <article className="flex flex-col">
      <DetailHeader document={data} />
      <StatusBlock status={data.status} />
      <Facts document={data} />
      <ChunkList
        chunks={data.chunks}
        chunkCount={data.chunk_count}
        processing={isProcessing(data.status)}
      />
    </article>
  )
}

/** 标题行：文件名、类型、解析状态与参考资料标记切换。 */
function DetailHeader({ document }: { document: DocumentDetailPayload }) {
  const setReference = useSetDocumentReference()
  const { toast } = useToast()

  function toggleReference() {
    setReference.mutate(
      { documentId: document.id, isReference: !document.is_reference },
      {
        onError: (error) => {
          toast({
            title: '参考资料标记没有切换成功',
            description: documentErrorMessage(error),
            tone: 'accent',
          })
        },
      },
    )
  }

  return (
    <header className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-black px-3 py-2">
      <div className="flex min-w-0 flex-wrap items-baseline gap-2">
        <h2 className="text-sm font-bold">{document.filename}</h2>
        <span className="text-xs uppercase">{document.file_type}</span>
        <DocumentStatusBadge status={document.status} />
      </div>
      <Button
        size="sm"
        variant={document.is_reference ? 'accent' : 'default'}
        aria-pressed={document.is_reference}
        disabled={setReference.isPending}
        title="标记为参考资料后，备课检索会加权，生成物里会溯源到这份资料。"
        onClick={toggleReference}
      >
        {document.is_reference ? '取消参考资料标记' : '标记为参考资料'}
      </Button>
    </header>
  )
}

/** 状态块：一句口径 + 该状态下的出路（等待解析 / 去裁决 / 重新上传）。 */
function StatusBlock({ status }: { status: ParseStatus }) {
  const openUpload = useKnowledgeUi((state) => state.openUpload)
  const attention = status === '有冲突' || status === '失败'

  return (
    <section
      className={cn(
        'flex flex-col gap-2 border-b-2 border-black border-l-8 px-3 py-2',
        attention ? 'border-l-[#ff3366]' : 'border-l-black',
      )}
    >
      <p className="text-sm">{STATUS_NOTE[status]}</p>
      {isProcessing(status) ? (
        <div aria-hidden="true" className="h-2 w-full max-w-sm rounded-none border-2 border-black">
          <div className="h-full w-1/2 bg-[#ff3366]" />
        </div>
      ) : null}
      {status === '有冲突' ? (
        <Link
          to="/conflicts?category=definition"
          className="self-start rounded-none border-2 border-black px-2 py-1 text-xs font-bold outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
        >
          去冲突审核区裁决
        </Link>
      ) : null}
      {status === '失败' ? (
        <Button size="sm" variant="accent" onClick={openUpload} className="self-start">
          重新上传
        </Button>
      ) : null}
    </section>
  )
}

/** 解析事实：完成时间、分块数、待审冲突数（工作台密度的键值行）。 */
function Facts({ document }: { document: DocumentDetailPayload }) {
  const facts = [
    { label: '解析完成时间', value: formatParsedAt(document.parsed_at) },
    { label: '分块', value: `${document.chunk_count} 个` },
    { label: '待审冲突', value: `${document.conflict_count} 个` },
  ]
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 border-b-2 border-black px-3 py-2 text-xs">
      {facts.map((fact) => (
        <div key={fact.label} className="flex items-baseline gap-2">
          <dt className="text-black/60">{fact.label}</dt>
          <dd>{fact.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** 分块明细：分块编号可回溯来源，`chunk_index` 是它在原文里的次序。 */
function ChunkList({
  chunks,
  chunkCount,
  processing,
}: {
  chunks: readonly DocumentChunk[]
  chunkCount: number
  processing: boolean
}) {
  return (
    <section className="flex flex-col">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-black px-3 py-2">
        <h3 className="text-sm font-bold">分块</h3>
        <span className="text-xs text-black/60">
          {chunkCount > chunks.length
            ? `共 ${chunkCount} 个，这里显示前 ${chunks.length} 个`
            : `${chunkCount} 个`}
        </span>
      </header>
      {chunks.length === 0 ? (
        <p className="px-3 py-3 text-xs text-black/60">
          {processing
            ? '分块会在解析完成后出现在这里。'
            : '这份资料没有分块：解析没有成功或内容为空。'}
        </p>
      ) : (
        <ol className="flex flex-col">
          {chunks.map((chunk) => (
            <li key={chunk.chunk_id} className="border-b-2 border-black px-3 py-2">
              <div className="flex items-baseline gap-2 text-xs text-black/60">
                <span className="font-bold text-black">分块 {chunk.chunk_index + 1}</span>
                <span>编号 {chunk.chunk_id}</span>
              </div>
              <p className="mt-1 text-sm leading-6 whitespace-pre-wrap">{chunk.content}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
