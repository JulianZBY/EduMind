/**
 * 新建备课会话：标题（可留空）、追问粒度三档、从知识库勾参考资料。
 *
 * 只在打开时挂载（父级按 `?new=1` 决定渲染与否），因此每次打开都是干净的初值，
 * 不需要在生效里重置表单。提交成功后直接进这一次备课（URL 即路由）。
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { Field, Label } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'
import { useToast } from '../../components/ui/useToast'
import { GranularityPicker } from './GranularityPicker'
import { ReferencePicker } from './ReferencePicker'
import type { Granularity } from './queries'
import { useCreateSession } from './queries'
import { sessionPath } from './routes'

export interface NewSessionDialogProps {
  /** 关闭（取消、Esc、遮罩点击都走这里）：父级据此清掉地址上的 `?new=1`。 */
  onClose: () => void
}

export function NewSessionDialog({ onClose }: NewSessionDialogProps) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const create = useCreateSession()
  const [title, setTitle] = useState('')
  const [granularity, setGranularity] = useState<Granularity>('标准')
  const [referenceIds, setReferenceIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    setError(null)
    create.mutate(
      { title, granularity, reference_doc_ids: referenceIds },
      {
        onSuccess: (session) => {
          toast({ title: '已新建备课会话', description: session.title, tone: 'default' })
          onClose()
          navigate(sessionPath(session.id))
        },
        onError: () => {
          setError('没建成：后端暂时取不到会话。确认后端已启动后重试，输入的内容还在。')
        },
      },
    )
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="新建备课会话"
      description="标题可以留空：首轮需求会自动充当标题。"
      size="md"
      footer={
        <>
          <Button size="sm" onClick={onClose}>
            取消
          </Button>
          <Button variant="accent" size="sm" disabled={create.isPending} onClick={submit}>
            {create.isPending ? '正在新建…' : '发起备课'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field htmlFor="new-session-title" label="标题" hint="留空时用首轮需求的前 30 个字标题。">
          <Input
            id="new-session-title"
            value={title}
            autoFocus
            placeholder="例如：一次函数（初二）"
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>

        <GranularityPicker value={granularity} onChange={setGranularity} disabled={create.isPending} />

        <div className="flex flex-col gap-1">
          <Label>本次备课的参考资料</Label>
          <ReferencePicker selectedIds={referenceIds} onChange={setReferenceIds} />
        </div>

        {error ? <p className="text-xs font-bold text-[#ff3366]">{error}</p> : null}
      </div>
    </Dialog>
  )
}
