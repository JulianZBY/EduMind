/**
 * 删除教学资料对话框（票 07）：级联不静默——对话框列出的就是会发生的全部。
 *
 * 数据来自删除前预览端点（默认勾选口径）：必删的分块与向量、文献笔记、待审冲突；
 * 「同时删除仅来源于此资料的知识点」默认勾选，不勾则这些知识点保留、来源引用清空；
 * 被题目考查的知识点在此列出受影响题目（确认后题目保留、考查关系置空）。
 * 破坏性动作二次确认，确认按钮用强调色底（风格文档第 3 节）。
 */
import { useId, useState } from 'react'
import { useNavigate } from 'react-router'
import type { DocumentDetail as DocumentDetailPayload } from '../../api/generated'
import { Button } from '../../components/ui/Button'
import { Checkbox } from '../../components/ui/Checkbox'
import { Dialog } from '../../components/ui/Dialog'
import { InfoIcon } from '../../components/ui/icons'
import { useToast } from '../../components/ui/useToast'
import { documentErrorMessage, useDeleteDocument, useDocumentDeletePreview } from './queries'

/** 固定会发生的必删项（预览端点计数照实回，缺席也如实说）。 */
function MandatoryLosses({
  chunkCount,
  literatureNotePresent,
  pendingConflictCount,
}: {
  chunkCount: number
  literatureNotePresent: boolean
  pendingConflictCount: number
}) {
  const noteText = literatureNotePresent ? '文献笔记 1 张' : '文献笔记：这份资料没有文献笔记'
  return (
    <ul className="flex flex-col gap-1 text-sm leading-6">
      <li>教学资料记录随资料删除；如有本地原件，一并删除</li>
      <li>分块与向量：{chunkCount} 个，全部清除</li>
      <li>{noteText}，随资料删除</li>
      <li>
        待审冲突：{pendingConflictCount > 0 ? `${pendingConflictCount} 条撤下` : '没有引用这份资料的待审冲突'}
        （已裁决的冲突记录保留）
      </li>
    </ul>
  )
}

export function DeleteDocumentDialog({
  document,
  onClose,
}: {
  document: DocumentDetailPayload
  onClose: () => void
}) {
  const navigate = useNavigate()
  const optionId = useId()
  const { toast } = useToast()
  const preview = useDocumentDeletePreview(document.id)
  // 对话框口径（票面原文）：「同时删除仅来源于此资料的知识点」默认勾选
  const [deleteSingleSource, setDeleteSingleSource] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const remove = useDeleteDocument()

  const data = preview.data
  const affected = deleteSingleSource ? (data?.affected_questions ?? []) : []

  const submit = () => {
    setError(null)
    remove.mutate(
      { documentId: document.id, deleteSingleSourceKnowledge: deleteSingleSource },
      {
        onSuccess: (result) => {
          const kept = result.knowledge_kept.length
          const removed = result.knowledge_deleted.length
          toast({
            title: '资料已删除',
            tone: 'default',
            description: [
              `分块与向量 ${result.chunks_deleted} 个已清除`,
              result.conflicts_withdrawn > 0 ? `待审冲突 ${result.conflicts_withdrawn} 条撤下` : '',
              removed > 0 ? `知识点删除 ${removed} 个` : '',
              kept > 0 ? `知识点保留 ${kept} 个（来源引用已摘除）` : '',
              result.questions_cleared.length > 0
                ? `${result.questions_cleared.length} 道题对被删知识点的考查关系已移除（题目保留）`
                : '',
            ]
              .filter(Boolean)
              .join('；'),
          })
          onClose()
          navigate('/knowledge')
        },
        onError: (cause) => setError(documentErrorMessage(cause)),
      },
    )
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="删除教学资料"
      description={document.filename}
      size="md"
      footer={
        <>
          <Button size="sm" onClick={onClose}>
            取消
          </Button>
          <Button
            size="sm"
            variant="accent"
            disabled={remove.isPending || preview.isPending || preview.isError || !data}
            onClick={submit}
          >
            {remove.isPending ? '正在删除…' : '删除资料'}
          </Button>
        </>
      }
    >
      {preview.isPending ? (
        <p className="text-sm text-black/60">正在核对这次删除会发生的每一件事…</p>
      ) : preview.isError || !data ? (
        <div className="flex flex-col gap-2">
          <p className="flex items-start gap-2 rounded-none border-2 border-[#ff3366] p-2 text-sm font-bold text-[#ff3366]" role="alert">
            <InfoIcon className="shrink-0" />
            删除后果没有核对出来：{documentErrorMessage(preview.error)}
          </p>
          <Button size="sm" onClick={() => preview.refetch()}>
            重试
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <section aria-label="一定会发生的删除">
            <p className="pb-1 text-xs text-black/60">删除后这些内容立即消失，不可找回：</p>
            <MandatoryLosses
              chunkCount={data.chunk_count}
              literatureNotePresent={data.literature_note_present}
              pendingConflictCount={data.pending_conflict_count}
            />
          </section>

          <section aria-label="知识点的去向" className="flex flex-col gap-2">
            <div className="flex items-start gap-2 text-sm leading-6">
              <Checkbox
                id={optionId}
                checked={deleteSingleSource}
                disabled={remove.isPending}
                onCheckedChange={(checked) => setDeleteSingleSource(checked === true)}
                className="mt-1"
              />
              <label htmlFor={optionId}>
                同时删除仅来源于此资料的知识点（默认勾选，共 {data.knowledge_single_source.length} 个）；
                不勾则保留这些知识点，只清空它们对本资料的来源引用。
              </label>
            </div>
            <p className="text-xs leading-5 text-black/60">
              删除知识点时，与它们相连的关系一并删除；未删除知识点之间的关系保留。
            </p>
            {data.knowledge_multi_source.length > 0 ? (
              <p className="text-xs leading-5 text-black/60">
                另有 {data.knowledge_multi_source.length} 个多来源知识点：摘除本资料的来源引用，知识点本身保留。
              </p>
            ) : null}
            {deleteSingleSource && data.knowledge_single_source.length > 0 ? (
              <ul className="flex flex-wrap gap-1">
                {data.knowledge_single_source.map((point) => (
                  <li
                    key={point.id}
                    className="rounded-none border-2 border-black px-2 py-1 text-xs font-bold"
                  >
                    {point.title}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <section aria-label="受影响的题目" className="flex flex-col gap-1">
            <p className="text-xs text-black/60">被题目考查的知识点：</p>
            {affected.length === 0 ? (
              <p className="text-sm leading-6">
                {deleteSingleSource
                  ? '没有题目考查将被删除的知识点，题库不受影响。'
                  : '知识点全部保留，题库不受影响。'}
              </p>
            ) : (
              <>
                <p className="text-sm leading-6">
                  {affected.length} 道题考查了将被删除的知识点：题目保留，仅移除对被删知识点的考查关系。
                </p>
                <ul className="flex flex-col">
                  {affected.map((question) => (
                    <li
                      key={question.id}
                      className="rounded-none border-2 border-black px-2 py-1 text-xs leading-5"
                    >
                      {question.content}
                      <span className="text-black/60">
                        （考查：{question.knowledge_titles.join('、')}）
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <p className="text-xs leading-5 text-black/60">
            生成物的历史版本不改写：已有课件、教案等里的溯源文本按原样留痕。
          </p>
          {error ? (
            <p className="flex items-start gap-2 rounded-none border-2 border-[#ff3366] p-2 text-xs font-bold text-[#ff3366]" role="alert">
              <InfoIcon className="shrink-0" />
              {error}
            </p>
          ) : null}
        </div>
      )}
    </Dialog>
  )
}
