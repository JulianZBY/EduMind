/**
 * 修改意见弹层：对**所选生成物**提修改意见再生成（产出新版本，不推翻别的结果）。
 *
 * 边界（CONTEXT.md「修改意见」）：只影响所选生成物——弹层把这一版的内容快照连同意见与
 * 基线版本发给服务端（`base_version_id`），因此同次备课的其它生成物一个版本都不多；
 * 服务端据此产出版本号更高的新版本，基线版本保持可回看、可下载。
 *
 * 三个状态都在这里：读取所选版本（进行中）→ 填写意见 → 修改进行中 / 失败可重试。
 */
import { useState } from 'react'
import { ApiError } from '../../api/client'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import { Textarea } from '../../components/ui/Textarea'
import { useToast } from '../../components/ui/useToast'
import { revisionFailureMessage, versionLabel } from './narrowing'
import type { ArtifactVersion } from './queries'
import { useArtifactVersion, useReviseArtifact } from './queries'

/** 修改进行中的说法：教师要知道后端在做什么、失败后能不能重试。 */
function revisionFailure(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 502) return '模型这次没给出可用的结果：内容没落盘，重试即可。'
    return revisionFailureMessage(error)
  }
  return revisionFailureMessage(error)
}

export interface ReviseDialogProps {
  sessionId: string
  /** 所选的那一版（基线版本）。 */
  version: ArtifactVersion
  onClose: () => void
  /** 产出新版本后（时间线要跟着刷新，由调用方的 mutation 失效缓存负责）。 */
  onRevised: (versionId: string | null, version: number | null) => void
}

export function ReviseDialog({ sessionId, version, onClose, onRevised }: ReviseDialogProps) {
  const { toast } = useToast()
  const detail = useArtifactVersion(version.id)
  const revise = useReviseArtifact()
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    const trimmed = feedback.trim()
    if (!trimmed) {
      setError('先写一句修改意见：说清改哪一处、改成什么样。')
      return
    }
    setError(null)
    revise.mutate(
      {
        artifactType: version.artifact_type,
        sessionId,
        baseVersionId: version.id,
        feedback: trimmed,
        content: detail.data?.content ?? null,
      },
      {
        onSuccess: (outcome) => {
          toast({
            title: `已产出${outcome.version === null ? '新版本' : versionLabel(outcome.version)}`,
            description: `按修改意见重做的${version.artifact_type}已入库；${versionLabel(version.version)}保持可取回。`,
            tone: 'default',
          })
          onRevised(outcome.versionId, outcome.version)
          onClose()
        },
        onError: (failure) => setError(revisionFailure(failure)),
      },
    )
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title={`对${version.artifact_type}提修改意见`}
      description={`只影响这一份${version.artifact_type}（以${versionLabel(version.version)}为基线），产出新版本而不是覆盖旧版。`}
      footer={
        <>
          <Button size="sm" onClick={onClose}>
            取消
          </Button>
          <Button
            variant="accent"
            size="sm"
            disabled={revise.isPending || detail.isPending || detail.isError}
            onClick={submit}
          >
            {revise.isPending ? '正在按修改意见重做…' : '按修改意见重做'}
          </Button>
        </>
      }
    >
      {detail.isPending ? (
        <p role="status" className="text-sm leading-6">
          正在读取{versionLabel(version.version)}的内容…
        </p>
      ) : detail.isError ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm leading-6">
            这一版的内容取不到了：后端暂时取不回它的内容快照，因此不能以它为基线修改。已入库的版本不会丢。
          </p>
          <Button size="sm" onClick={() => void detail.refetch()}>
            重试
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <Field
            htmlFor="revise-feedback"
            label="修改意见"
            hint={`例如：把第二页的例子换成生活情境；某个小节补一条易错点。写完点「按修改意见重做」。`}
            error={error ?? undefined}
          >
            <Textarea
              id="revise-feedback"
              rows={3}
              autoFocus
              value={feedback}
              placeholder="说清要改哪一处、改成什么样…"
              onChange={(event) => setFeedback(event.target.value)}
            />
          </Field>
          <p className="text-xs leading-5 text-black/60">
            这次修改只作用于当前所选生成物；同次备课的其它生成物不受影响。原版本（
            {versionLabel(version.version)}）会一直保留，可回看、可下载。
          </p>
        </div>
      )}
    </Dialog>
  )
}
