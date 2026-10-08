/**
 * 会话改名（inline，票 04）：就地一个输入框 + 保存/取消，走既有
 * `PATCH /api/v1/sessions/{id}`，不弹层。会话头与侧栏行共用本表单；
 * 教师手动改名后自动命名停用（服务端 `title_edited` 标记，这里只管改名）。
 */
import { useState } from 'react'
import { ApiError } from '../../api/client'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import type { SessionSummary } from './queries'
import { useUpdateSession } from './queries'

export interface SessionRenameFormProps {
  session: SessionSummary
  /** 改完（保存成功或取消）退出编辑态。 */
  onDone: () => void
}

export function SessionRenameForm({ session, onDone }: SessionRenameFormProps) {
  const update = useUpdateSession()
  const [title, setTitle] = useState(session.title)
  const [error, setError] = useState<string | null>(null)

  const save = () => {
    const next = title.trim()
    if (!next) {
      setError('名字不能为空。')
      return
    }
    setError(null)
    update.mutate(
      { sessionId: session.id, patch: { title: next } },
      {
        onSuccess: onDone,
        onError: (failure) => {
          setError(
            failure instanceof ApiError && failure.status === 422
              ? '后端没接受这个名字：不能为空或全空白。'
              : '没改上：后端暂时改不了会话名，重试即可。',
          )
        },
      },
    )
  }

  return (
    <form
      className="flex flex-col gap-1"
      onSubmit={(event) => {
        event.preventDefault()
        save()
      }}
    >
      <div className="flex items-center gap-1">
        <Input
          value={title}
          autoFocus
          aria-label="会话名字"
          disabled={update.isPending}
          className="min-w-0 flex-1"
          onChange={(event) => setTitle(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') onDone()
          }}
        />
        <Button size="sm" variant="accent" type="submit" disabled={update.isPending || !title.trim()}>
          {update.isPending ? '正在保存…' : '保存'}
        </Button>
        <Button size="sm" disabled={update.isPending} onClick={onDone}>
          取消
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-xs font-bold text-[#ff3366]">
          {error}
        </p>
      ) : null}
    </form>
  )
}
