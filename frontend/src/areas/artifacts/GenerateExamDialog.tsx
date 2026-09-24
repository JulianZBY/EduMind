/**
 * 一键生成试卷弹层：按备课意图出题 → 题目自动入题库并标注考查知识点 → 试卷落一条新版本。
 *
 * 三个状态齐备：填写 → 进行中 → 失败可重试；成功后给出下载与「去题库按考查知识点查看」两个下一步。
 */
import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'
import { useToast } from '../../components/ui/useToast'
import { GeneratedLinks, GradeAndMinutesFields, PendingBar } from './GenerateDialogParts'
import { buildIntent, generationFailureMessage, producedVersionLabel } from './narrowing'
import { artifactDownloadUrl, useGenerateExam } from './queries'

export interface GenerateExamDialogProps {
  sessionId: string
  /** 主题初值（这次备课的标题）。 */
  defaultTopic: string
  onClose: () => void
  /** 生成出新版本后（时间线跟着刷新）。 */
  onGenerated: () => void
}

export function GenerateExamDialog({
  sessionId,
  defaultTopic,
  onClose,
  onGenerated,
}: GenerateExamDialogProps) {
  const { toast } = useToast()
  const generate = useGenerateExam(sessionId)
  const [topic, setTopic] = useState(defaultTopic)
  const [grade, setGrade] = useState('')
  const [minutes, setMinutes] = useState('')
  const [count, setCount] = useState('5')
  const [error, setError] = useState<string | null>(null)
  const result = generate.data ?? null

  const submit = () => {
    if (!topic.trim()) {
      setError('先写一个备课主题：试卷按它出题。')
      return
    }
    const n = Number.parseInt(count, 10)
    if (!Number.isFinite(n) || n < 1 || n > 20) {
      setError('题量填 1–20 之间的整数。')
      return
    }
    setError(null)
    generate.mutate(
      { intent: buildIntent({ topic, grade, minutes }), n },
      {
        onSuccess: (payload) => {
          onGenerated()
          toast({
            title: `已生成${producedVersionLabel(payload.version)}`,
            description:
              payload.bank_saved > 0
                ? `${payload.bank_saved} 道题已入题库，并标注了考查知识点。`
                : '题目没进题库（模型这次没给出可解析的题目）。',
            tone: 'default',
          })
        },
        onError: (failure) => setError(generationFailureMessage(failure, '试卷')),
      },
    )
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="一键生成试卷"
      description="按备课意图出题：题目自动入题库并标注考查知识点，试卷落一条新版本。"
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
            {generate.isPending ? '正在出题…' : result ? '已生成' : '生成试卷'}
          </Button>
        </>
      }
    >
      {generate.isPending ? (
        <PendingBar label="正在按备课意图出题，并写入题库…" />
      ) : result ? (
        <GeneratedLinks
          summary={`已产出${producedVersionLabel(result.version)}，${
            result.bank_saved > 0 ? `其中 ${result.bank_saved} 道题已入题库。` : '题目没进题库。'
          }`}
          primaryHref={artifactDownloadUrl(result.version_id ?? '')}
          primaryLabel="下载这份试卷"
          secondaryHref="/question-bank"
          secondaryLabel="去题库按考查知识点查看"
        />
      ) : (
        <div className="flex flex-col gap-3">
          <Field htmlFor="exam-topic" label="备课主题" hint="取自这次备课的标题，可改。">
            <Input
              id="exam-topic"
              value={topic}
              autoFocus
              onChange={(event) => setTopic(event.target.value)}
            />
          </Field>
          <GradeAndMinutesFields
            idPrefix="exam"
            grade={grade}
            onGrade={setGrade}
            minutes={minutes}
            onMinutes={setMinutes}
          />
          <Field
            htmlFor="exam-count"
            label="题量"
            hint="1–20 道；题型由模型覆盖选择 / 填空 / 简答。"
            error={error ?? undefined}
          >
            <Input
              id="exam-count"
              inputMode="numeric"
              value={count}
              onChange={(event) => setCount(event.target.value)}
            />
          </Field>
        </div>
      )}
    </Dialog>
  )
}
