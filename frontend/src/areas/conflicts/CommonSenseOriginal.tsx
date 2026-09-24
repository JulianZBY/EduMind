/**
 * 常识存疑的形态（CONTEXT.md 第 6 节）：红旗标记 + 原文 + 「编辑修正后入库」的编辑框。
 *
 * 这一类的问法不是「谁对」，而是「要不要让它进库」：所以这里只呈现**原文**，
 * 教师若选「编辑修正后入库」，落库的是他在下面改对后的内容（原文留在冲突记录里）。
 */
import { useId } from 'react'
import { Field, MarkerIcon } from '../../components/ui'

export interface CommonSenseOriginalProps {
  /** 原文：可能与事实不符的那段内容。 */
  original: string
  /** 教师改对后的内容（草稿住裁决卡，故由父组件持有）。 */
  revisedContent: string
  onRevisedChange: (value: string) => void
  disabled?: boolean
}

/** 文本域皮肤：与基线 `Input` 同一套四态（悬停加粗边线、聚焦可见、禁用降级）。 */
const textareaClasses = [
  'block min-h-24 w-full rounded-none border-2 border-black bg-white px-2 py-1 text-sm text-black',
  'transition-colors duration-150 outline-none placeholder:text-black/40',
  'hover:border-4 focus-visible:border-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black',
  'disabled:cursor-not-allowed disabled:border disabled:border-black/40 disabled:text-black/40',
].join(' ')

export function CommonSenseOriginal({
  original,
  revisedContent,
  onRevisedChange,
  disabled = false,
}: CommonSenseOriginalProps) {
  const fieldId = useId()

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-none border-2 border-[#ff3366] px-3 py-2">
        <p className="flex items-center gap-2 text-sm font-bold">
          <MarkerIcon className="shrink-0 text-[#ff3366]" />
          内容可能是错的常识，等你判断「要不要让它进库」
        </p>
        <p className="mt-2 text-xs text-black/60">原文</p>
        <p className="mt-1 text-sm leading-6 whitespace-pre-wrap text-black">
          {original || '（没有正文）'}
        </p>
      </div>

      <Field
        htmlFor={fieldId}
        label="修正后的内容"
        hint="改对了再入库：入库的是这份内容，原文会留在冲突记录里，两条都可以追溯。"
      >
        <textarea
          id={fieldId}
          className={textareaClasses}
          value={revisedContent}
          disabled={disabled}
          placeholder="在这里写下正确的说法…"
          onChange={(event) => onRevisedChange(event.target.value)}
        />
      </Field>
    </div>
  )
}
