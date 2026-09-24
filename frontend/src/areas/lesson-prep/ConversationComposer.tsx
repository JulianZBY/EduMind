/**
 * 对话轴的输入区：发送一轮备课、跳过追问、会话内上传资料。
 *
 * - **发送**：只把教师原话交给服务端（澄清还是生成由服务端状态机判定）；
 * - **跳过追问**（CONTEXT.md）：教师表示「信息够了，直接出结果」。服务端按**语义**判这个词组，
 *   不是关键词匹配，所以这里把「信息够了」这句话当成教师那一轮的话发出去；草稿里补的
 *   信息并入同一句话，一起进历史；
 * - **上传参考资料**：会话内上传的文件自动归入本次备课的参考资料（绑定动作在 `useAttachReference`）。
 */
import { useRef, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Textarea } from '../../components/ui/Textarea'

/** 跳过追问时替教师说的那句话：语义明确，服务端不靠字面词表判。 */
const SKIP_UTTERANCE = '信息够了，直接生成。'

/**
 * 组装跳过追问的原话：草稿里有补充信息就并进同一句（信息一起进历史），没有就用标准说法。
 */
function buildSkipUtterance(draft: string): string {
  const supplement = draft.trim()
  return supplement ? `${supplement}（${SKIP_UTTERANCE}）` : SKIP_UTTERANCE
}

export interface ConversationComposerProps {
  /** 发送一轮备课（本轮原话）。 */
  onSend: (utterance: string) => void
  /** 跳过追问：草稿作为补充信息一并发送，服务端按语义判定跳过。 */
  onSkip: (utterance: string) => void
  /** 上传一份资料并归入本次备课的参考资料。 */
  onUpload: (file: File) => void
  /** 一轮对话进行中：发送与跳过都不可用，避免重复提交。 */
  busy: boolean
  /** 正在上传资料。 */
  uploading: boolean
  /** 上传或绑定失败的说明（强调色文案）。 */
  uploadError: string | null
}

export function ConversationComposer({
  onSend,
  onSkip,
  onUpload,
  busy,
  uploading,
  uploadError,
}: ConversationComposerProps) {
  const [draft, setDraft] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const disabled = busy || uploading
  const canSend = draft.trim().length > 0 && !disabled

  const submit = () => {
    if (!canSend) return
    const utterance = draft.trim()
    setDraft('')
    onSend(utterance)
  }

  const skip = () => {
    if (disabled) return
    const utterance = buildSkipUtterance(draft)
    setDraft('')
    onSkip(utterance)
  }

  return (
    <footer className="border-t-2 border-black px-3 py-2">
      <Textarea
        aria-label="这一轮备课的需求"
        rows={2}
        value={draft}
        placeholder="说说这次备课：主题、学段、时长…（回车发送，Shift + 回车换行）"
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' || event.shiftKey) return
          event.preventDefault()
          submit()
        }}
      />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button variant="accent" size="sm" disabled={!canSend} onClick={submit}>
          {busy ? '正在备课…' : '发送'}
        </Button>
        <Button size="sm" disabled={disabled} onClick={skip}>
          跳过追问，直接生成
        </Button>
        <Button size="sm" disabled={disabled} onClick={() => fileInput.current?.click()}>
          上传参考资料
        </Button>
        <span className="text-xs text-black/60">回车发送，Shift + 回车换行</span>
      </div>

      {/* 文件输入自身不可见：键盘用户走「上传参考资料」按钮触发 */}
      <input
        ref={fileInput}
        type="file"
        tabIndex={-1}
        aria-hidden="true"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (file) onUpload(file)
        }}
      />

      <p className="mt-2 text-xs leading-5 text-black/60">
        {uploading
          ? '正在上传，并归入本次备课的参考资料…'
          : '会话内上传的文件自动归入本次备课的参考资料；解析状态在知识库区跟进。'}
      </p>
      {uploadError ? (
        <p className="mt-1 text-xs font-bold text-[#ff3366]">{uploadError}</p>
      ) : null}
    </footer>
  )
}
