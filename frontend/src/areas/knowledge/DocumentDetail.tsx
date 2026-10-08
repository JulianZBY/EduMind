/**
 * 主区：教学资料详情（工作台密度——贴边分隔线、紧凑行、一屏多信息）。
 *
 * 四块内容：状态与参考资料标记（可切换，即时生效）、文献笔记（资料概要 + 知识点索引，ADR-0007）、
 * 解析事实（完成时间 / 分块数 / 待审冲突）、入库的分块明细（可回溯来源）。
 * 资料仍在「处理中」时这里会随轮询自动刷新到终态。
 */
import { Link, useParams } from 'react-router'
import { useState } from 'react'
import type { DocumentChunk, DocumentDetail as DocumentDetailPayload, LiteratureNoteView } from '../../api/generated'
import { EmptyState } from '../../components/ui/EmptyState'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/useToast'
import { ProviderMissingNotice } from '../settings/ProviderMissingNotice'
import { cn } from '../../lib/cn'
import { DeleteDocumentDialog } from './DeleteDocumentDialog'
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
      <StatusBlock status={data.status} failureReason={data.failure_reason ?? ''} />
      <LiteratureNoteSection note={data.literature_note} processing={isProcessing(data.status)} />
      <Facts document={data} />
      <ChunkList
        chunks={data.chunks}
        chunkCount={data.chunk_count}
        processing={isProcessing(data.status)}
      />
    </article>
  )
}

/**
 * 文献笔记（CONTEXT.md「文献笔记」，ADR-0007）：资料概要 + 这份资料提取出的知识点索引。
 * 资料的管理入口从此落在文献笔记上；索引条目可点进知识图谱定位到知识点。
 */
function LiteratureNoteSection({ note, processing }: { note: LiteratureNoteView; processing: boolean }) {
  if (note.status === '未配置') {
    // 对话模型未配置：分块与解析照常入库，但笔记不生成——给去设置页的引导，不返回假摘要
    return (
      <section aria-label="文献笔记" className="border-b-2 border-black px-3 py-2">
        <NoteHeading source={note.source} />
        <ProviderMissingNotice message="文献笔记还没有生成：对话模型未配置。配置后重新上传这份资料即可生成。" />
      </section>
    )
  }
  if (note.status === '未生成') {
    return (
      <section aria-label="文献笔记" className="border-b-2 border-black px-3 py-2">
        <NoteHeading source={note.source} />
        <p className="text-xs text-black/60">
          {processing ? '文献笔记会在解析完成后自动生成。' : '这份资料没有文献笔记：解析没有成功，或概要生成没有成功。'}
        </p>
      </section>
    )
  }
  return (
    <section aria-label="文献笔记" className="flex flex-col border-b-2 border-black">
      <NoteHeading source={note.source} />
      <p className="border-b-2 border-black px-3 py-2 text-sm leading-6">{note.summary}</p>
      <KnowledgeIndex entries={note.knowledge_index} />
    </section>
  )
}

/** 文献笔记栏头：术语「文献笔记」照用，来源（教学资料 / 网页）随行标注。 */
function NoteHeading({ source }: { source: string }) {
  return (
    <header className="flex items-center justify-between gap-2 px-3 pb-1 pt-2">
      <h3 className="text-sm font-bold">文献笔记</h3>
      <span className="text-xs text-black/60">来源：{source}</span>
    </header>
  )
}

/** 知识点索引：这份资料提取出的知识点，条目可点进知识图谱。 */
function KnowledgeIndex({ entries }: { entries: LiteratureNoteView['knowledge_index'] }) {
  return (
    <div className="px-3 pb-2">
      <p className="pt-1 text-xs text-black/60">知识点索引（{entries.length}）</p>
      <ul className="mt-1 flex flex-wrap gap-1">
        {entries.map((entry) => (
          <li key={entry.id}>
            <Link
              to={`/knowledge-graph/${entry.id}`}
              title="到知识图谱查看这个知识点"
              className="inline-block rounded-none border-2 border-black px-2 py-1 text-xs font-bold outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
            >
              {entry.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** 标题行：文件名、类型、解析状态与参考资料标记切换。 */
function DetailHeader({ document }: { document: DocumentDetailPayload }) {
  const setReference = useSetDocumentReference()
  const { toast } = useToast()
  const [deleting, setDeleting] = useState(false)

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
      <div className="flex items-center gap-2">
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
        <Button
          size="sm"
          disabled={isProcessing(document.status)}
          title={isProcessing(document.status)
            ? '教学资料正在处理中，暂不可删除。请等待处理结束后再试。'
            : '删除这份资料：联动后果会在对话框里一次交代清楚。'}
          onClick={() => setDeleting(true)}
        >
          删除资料
        </Button>
      </div>
      {isProcessing(document.status) ? (
        <p className="text-xs text-black/60">教学资料正在处理中，暂不可删除。请等待处理结束后再试。</p>
      ) : null}
      {deleting ? <DeleteDocumentDialog document={document} onClose={() => setDeleting(false)} /> : null}
    </header>
  )
}

/** 状态块：一句口径 + 该状态下的出路（等待解析 / 去裁决 / 重新上传）。 */
function StatusBlock({ status, failureReason }: { status: ParseStatus; failureReason: string }) {
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
      {status === '失败' && failureReason ? (
        <p className="text-sm font-bold">原因：{failureReason}</p>
      ) : null}
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
