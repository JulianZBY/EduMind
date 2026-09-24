/**
 * 按意图生成互动内容弹层：生成单文件 HTML5（小游戏 / 知识点动画）→ 落一条新版本 →
 * 教师点链接在新标签页打开试用。
 *
 * 三个状态齐备：填写 → 进行中 → 失败可重试（502 = 模型没给出单文件 HTML，没落半成品）。
 */
import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'
import { useToast } from '../../components/ui/useToast'
import { GeneratedLinks, GradeAndMinutesFields, PendingBar } from './GenerateDialogParts'
import { buildIntent, generationFailureMessage, producedVersionLabel } from './narrowing'
import { artifactDownloadUrl, useGenerateInteractive } from './queries'

export interface GenerateInteractiveDialogProps {
  sessionId: string
  /** 主题初值（这次备课的标题）。 */
  defaultTopic: string
  onClose: () => void
  /** 生成出新版本后（时间线跟着刷新）。 */
  onGenerated: () => void
}

export function GenerateInteractiveDialog({
  sessionId,
  defaultTopic,
  onClose,
  onGenerated,
}: GenerateInteractiveDialogProps) {
  const { toast } = useToast()
  const generate = useGenerateInteractive(sessionId)
  const [topic, setTopic] = useState(defaultTopic)
  const [grade, setGrade] = useState('')
  const [minutes, setMinutes] = useState('')
  const [interactivity, setInteractivity] = useState('')
  const [error, setError] = useState<string | null>(null)
  const result = generate.data ?? null

  const submit = () => {
    if (!topic.trim()) {
      setError('先写一个备课主题：互动内容按它生成。')
      return
    }
    setError(null)
    generate.mutate(buildIntent({ topic, grade, minutes, interactivity }), {
      onSuccess: (payload) => {
        onGenerated()
        toast({
          title: `已生成${producedVersionLabel(payload.version)}`,
          description: '可在弹层里直接在新标签页打开试用。',
          tone: 'default',
        })
      },
      onError: (failure) => setError(generationFailureMessage(failure, '互动内容')),
    })
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="生成互动内容"
      description="按备课意图生成单文件 HTML5 小游戏或知识点动画，产出新版本后可立即试用。"
      footer={
        <>
          <Button size="sm" onClick={onClose}>
            {result ? '完成' : '取消'}
          </Button>
          <Button
            variant="accent"
            size="sm"
            disabled={generate.isPending || Boolean(result)}
            onClick={submit}
          >
            {generate.isPending ? '正在生成…' : result ? '已生成' : '生成互动内容'}
          </Button>
        </>
      }
    >
      {generate.isPending ? (
        <PendingBar label="正在生成单文件 HTML5 互动内容…" />
      ) : result ? (
        <GeneratedLinks
          summary={`已产出${producedVersionLabel(result.version)}（${result.html.length} 字符的单文件 HTML5）。`}
          primaryHref={artifactDownloadUrl(result.version_id ?? '', { openInTab: true })}
          primaryLabel="在新标签页打开试用"
          primaryOpenInTab
        />
      ) : (
        <div className="flex flex-col gap-3">
          <Field htmlFor="interactive-topic" label="备课主题" hint="取自这次备课的标题，可改。">
            <Input
              id="interactive-topic"
              value={topic}
              autoFocus
              onChange={(event) => setTopic(event.target.value)}
            />
          </Field>
          <GradeAndMinutesFields
            idPrefix="interactive"
            grade={grade}
            onGrade={setGrade}
            minutes={minutes}
            onMinutes={setMinutes}
          />
          <Field
            htmlFor="interactive-appeal"
            label="互动诉求（可不填）"
            hint="如：课堂小游戏，判断哪些是一次函数；知识点动画，演示三次握手。"
            error={error ?? undefined}
          >
            <Input
              id="interactive-appeal"
              value={interactivity}
              placeholder="想让学生动手做什么…"
              onChange={(event) => setInteractivity(event.target.value)}
            />
          </Field>
        </div>
      )}
    </Dialog>
  )
}
