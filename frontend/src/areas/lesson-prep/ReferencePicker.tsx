/**
 * 参考资料勾选清单：从知识库的教学资料里勾出本次备课要用的那几份。
 *
 * 勾选结果交给服务端（新建会话时是 `reference_doc_ids`，会话中改是
 * `PATCH /api/v1/sessions/{id}`）——只有被勾选的资料才加权并溯源（CONTEXT.md「参考资料」）。
 * 解析还没结束（处理中）或解析失败（失败）的资料勾不了，界面直接说明原因，不让教师白勾。
 */
import { Button } from '../../components/ui/Button'
import { isUsableReference } from './narrowing'
import type { KnowledgeDocument } from './narrowing'
import { useKnowledgeDocuments } from './queries'

const rowBase = [
  'flex w-full items-start gap-2 rounded-none border-b-2 border-black px-3 py-2 text-left',
  'outline-none transition-colors duration-150 hover:bg-black hover:text-white',
  'focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black',
  'disabled:pointer-events-none disabled:border-b disabled:border-black/40 disabled:text-black/40',
].join(' ')

function DocumentRow({
  document,
  checked,
  onToggle,
}: {
  document: KnowledgeDocument
  checked: boolean
  onToggle: () => void
}) {
  const usable = isUsableReference(document)

  return (
    <li className="border-b-2 border-black last:border-b-0">
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={!usable}
        onClick={onToggle}
        className={`group ${rowBase}`}
      >
        <span
          aria-hidden="true"
          className={`mt-0.5 h-3.5 w-3.5 shrink-0 rounded-none border-2 border-black ${
            checked ? 'bg-[#ff3366]' : 'bg-white'
          }`}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm">{document.filename}</span>
          <span className="block text-xs text-black/60 group-hover:text-white">
            {document.status}
            {usable ? '' : '：解析完成后才能勾选'}
          </span>
        </span>
        {checked ? <span className="shrink-0 text-xs font-bold">已勾选</span> : null}
      </button>
    </li>
  )
}

export interface ReferencePickerProps {
  /** 已勾选的资料 id（来自服务端会话设置）。 */
  selectedIds: readonly string[]
  onChange: (ids: string[]) => void
}

export function ReferencePicker({ selectedIds, onChange }: ReferencePickerProps) {
  const documents = useKnowledgeDocuments()

  const toggle = (id: string) => {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((current) => current !== id)
        : [...selectedIds, id],
    )
  }

  return (
    <section aria-label="参考资料" className="flex flex-col gap-1">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-bold">参考资料</span>
        <span className="text-xs text-black/60">已勾选 {selectedIds.length} 份</span>
      </div>
      <p className="text-xs text-black/60">
        只有被勾选的资料会在本次备课里加权，并在生成回复里溯源；不勾也能备课，只是不溯源。
      </p>

      {documents.isPending ? (
        <div className="border-2 border-black px-3 py-3" role="status">
          <p className="text-xs">正在读取知识库…</p>
          <div className="mt-2 h-1.5 w-full rounded-none border-2 border-black">
            <div className="h-full w-1/3 bg-black" />
          </div>
        </div>
      ) : null}

      {documents.isError ? (
        <div className="border-2 border-black px-3 py-3" role="alert">
          <p className="text-xs font-bold text-[#ff3366]">知识库取不到资料</p>
          <p className="mt-1 text-xs leading-5">确认后端已启动后可重试，已入库的资料不会丢。</p>
          <Button size="sm" className="mt-2" onClick={() => void documents.refetch()}>
            重试
          </Button>
        </div>
      ) : null}

      {documents.data && documents.data.length === 0 ? (
        <p className="border-2 border-black px-3 py-3 text-xs leading-5 text-black/60">
          知识库还没有教学资料。先到知识库区上传，再回来勾选；也可以在会话里直接上传（会自动归入本次备课的参考资料）。
        </p>
      ) : null}

      {documents.data && documents.data.length > 0 ? (
        <ul className="rounded-none border-2 border-black">
          {documents.data.map((document) => (
            <DocumentRow
              key={document.id}
              document={document}
              checked={selectedIds.includes(document.id)}
              onToggle={() => toggle(document.id)}
            />
          ))}
        </ul>
      ) : null}
    </section>
  )
}
