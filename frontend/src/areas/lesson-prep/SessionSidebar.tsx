/**
 * 二级侧栏 = 备课会话列表：新建 / 重命名 / 删除 / 检索，全部与服务端状态同步。
 *
 * 浏览器里没有会话事实：列表来自 `GET /api/v1/sessions`（检索走后端的标题过滤 `q=`），
 * 增删改都打到服务端再让 Query 失效重取。浏览器侧会话存储已在票 04 退场，
 * 本区不得再引入任何浏览器侧的会话事实源。
 */
import { useRef, useState } from 'react'
import { NavLink, useNavigate, useParams, useSearchParams } from 'react-router'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { WorkbenchSidebar } from '../../components/layout/Workbench'
import { ApiError } from '../../api/client'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../../components/ui/DropdownMenu'
import { Field } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'
import { useToast } from '../../components/ui/useToast'
import { cn } from '../../lib/cn'
import { formatTimestamp } from './format'
import { NewSessionDialog } from './NewSessionDialog'
import type { SessionSummary } from './queries'
import { useDeleteSession, useSessions, useUpdateSession } from './queries'
import { LESSON_PREP_PATH, sessionPath } from './routes'

/** 检索输入停顿多久后才落到地址上（地址即检索条件，但不逐键改 URL）。 */
const SEARCH_DEBOUNCE_MS = 250

/** 一行会话：标题 + 消息数 / 追问粒度 / 最近使用时间；当前行是黑白反色 + 强调色左边线。 */
function SessionRow({
  session,
  search,
  onRenameRequest,
  onDeleteRequest,
}: {
  session: SessionSummary
  /** 选中会话时保留的检索条件（进会话不丢筛选，与题库区同一口径）。 */
  search: string
  onRenameRequest: (session: SessionSummary) => void
  onDeleteRequest: (session: SessionSummary) => void
}) {
  return (
    <li className="border-b-2 border-black">
      <div className="flex items-stretch">
        <NavLink
          to={{ pathname: sessionPath(session.id), search }}
          className={({ isActive }) =>
            cn(
              'flex min-w-0 flex-1 flex-col gap-1 border-l-4 px-3 py-2 outline-none transition-colors duration-150',
              'hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black',
              isActive ? 'border-l-[#ff3366] bg-black text-white' : 'border-l-transparent',
            )
          }
        >
          <span className="truncate text-sm font-bold">{session.title}</span>
          <span className="text-xs">
            消息 {session.message_count} 条 · 追问粒度 {session.granularity}
            {session.reference_doc_ids.length > 0
              ? ` · 参考资料 ${session.reference_doc_ids.length} 份`
              : ''}
          </span>
          <span className="text-xs">最近使用 {formatTimestamp(session.updated_at)}</span>
        </NavLink>
        <div className="flex shrink-0 items-center border-l-2 border-black px-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" aria-label={`更多操作：${session.title}`}>
                更多
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onSelect={() => onRenameRequest(session)}>重命名</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onDeleteRequest(session)}>删除会话</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </li>
  )
}

/** 重命名弹层：改的是服务端会话标题（列表与标题条都以服务端为准）。 */
function RenameDialog({ session, onClose }: { session: SessionSummary; onClose: () => void }) {
  const { toast } = useToast()
  const update = useUpdateSession()
  const [title, setTitle] = useState(session.title)
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    const next = title.trim()
    if (!next) {
      setError('标题不能为空；要清掉标题请改成别的名字。')
      return
    }
    setError(null)
    update.mutate(
      { sessionId: session.id, patch: { title: next } },
      {
        onSuccess: (updated) => {
          toast({ title: '已重命名备课会话', description: updated.title, tone: 'default' })
          onClose()
        },
        onError: (failure) => {
          setError(
            failure instanceof ApiError && failure.status === 422
              ? '后端没接受这个标题：不能为空或全空白。'
              : '没改上：后端暂时改不了会话标题，重试即可。',
          )
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
      title="重命名备课会话"
      description="只改标题，对话与生成物都不动。"
      size="sm"
      footer={
        <>
          <Button size="sm" onClick={onClose}>
            取消
          </Button>
          <Button variant="accent" size="sm" disabled={update.isPending} onClick={submit}>
            {update.isPending ? '正在保存…' : '保存标题'}
          </Button>
        </>
      }
    >
      <Field htmlFor={`rename-${session.id}`} label="标题" error={error ?? undefined}>
        <Input
          id={`rename-${session.id}`}
          value={title}
          autoFocus
          onChange={(event) => setTitle(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') submit()
          }}
        />
      </Field>
    </Dialog>
  )
}

/** 删除弹层：破坏性动作必须二次确认，确认按钮用强调色底。 */
function DeleteDialog({
  session,
  onClose,
  onDeleted,
}: {
  session: SessionSummary
  onClose: () => void
  onDeleted: () => void
}) {
  const remove = useDeleteSession()
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    setError(null)
    remove.mutate(session.id, {
      onSuccess: onDeleted,
      onError: () => setError('没删掉：后端暂时删不了这个会话，重试即可。'),
    })
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="删除备课会话"
      description={session.title}
      size="sm"
      footer={
        <>
          <Button size="sm" onClick={onClose}>
            取消
          </Button>
          <Button variant="accent" size="sm" disabled={remove.isPending} onClick={submit}>
            {remove.isPending ? '正在删除…' : '删除会话'}
          </Button>
        </>
      }
    >
      <p className="text-sm leading-6">
        删除后这次备课的全部对话都不再出现，且不可找回。生成物文件不受影响。
      </p>
      {error ? <p className="mt-2 text-xs font-bold text-[#ff3366]">{error}</p> : null}
    </Dialog>
  )
}

export function SessionSidebar() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { sessionId: currentSessionId } = useParams()
  const navigate = useNavigate()
  const { toast } = useToast()
  const keyword = searchParams.get('q') ?? ''
  const [draft, setDraft] = useState(keyword)
  const sessions = useSessions(keyword)
  const [renameTarget, setRenameTarget] = useState<SessionSummary | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<SessionSummary | null>(null)
  const debounce = useRef<number | null>(null)

  const newSessionOpen = searchParams.get('new') === '1'
  /** 选中会话、删除后回列表时保留的检索条件。 */
  const listSearch = keyword ? `?${new URLSearchParams({ q: keyword }).toString()}` : ''

  const writeKeyword = (value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value.trim()) next.set('q', value)
    else next.delete('q')
    setSearchParams(next, { replace: true })
  }

  const changeKeyword = (value: string) => {
    setDraft(value)
    if (debounce.current !== null) window.clearTimeout(debounce.current)
    debounce.current = window.setTimeout(() => writeKeyword(value), SEARCH_DEBOUNCE_MS)
  }

  const clearKeyword = () => {
    if (debounce.current !== null) window.clearTimeout(debounce.current)
    setDraft('')
    writeKeyword('')
  }

  const setNewSessionOpen = (open: boolean) => {
    const next = new URLSearchParams(searchParams)
    if (open) next.set('new', '1')
    else next.delete('new')
    setSearchParams(next, { replace: !open })
  }

  const handleDeleted = (deleted: SessionSummary) => {
    toast({ title: '已删除备课会话', description: deleted.title, tone: 'accent' })
    setDeleteTarget(null)
    if (deleted.id === currentSessionId) {
      navigate({ pathname: LESSON_PREP_PATH, search: listSearch })
    }
  }

  const list = sessions.data?.sessions
  const total = list?.length ?? 0

  return (
    <>
      <WorkbenchSidebar
        title="会话列表"
        meta={sessions.data ? `${total} 个会话` : '读取中…'}
        actions={
          <Button size="sm" onClick={() => setNewSessionOpen(true)}>
            新建会话
          </Button>
        }
      >
        <div className="flex flex-wrap items-center gap-2 border-b-2 border-black px-3 py-2">
          <Input
            className="min-w-0 flex-1"
            value={draft}
            aria-label="按标题检索会话"
            placeholder="按标题检索会话"
            onChange={(event) => changeKeyword(event.target.value)}
          />
          {keyword ? (
            <Button size="sm" onClick={clearKeyword}>
              清除检索
            </Button>
          ) : null}
        </div>

        {sessions.isPending ? <SidebarNote>正在读取会话列表…</SidebarNote> : null}

        {sessions.isError ? (
          <div className="border-b-2 border-black px-3 py-3" role="alert">
            <p className="text-xs font-bold text-[#ff3366]">会话列表取不到</p>
            <p className="mt-1 text-xs leading-5">
              后端暂时取不到备课会话。已入库的会话不会丢，确认后端已启动后可重试。
            </p>
            <Button size="sm" className="mt-2" onClick={() => void sessions.refetch()}>
              重试
            </Button>
          </div>
        ) : null}

        {list && list.length === 0 ? (
          <SidebarNote>
            {keyword
              ? `没有标题含「${keyword}」的备课会话。清除检索看看全部会话。`
              : '还没有备课会话。新建一次备课后，会话会出现在这里。'}
          </SidebarNote>
        ) : null}

        {list && list.length > 0 ? (
          <ul>
            {list.map((session) => (
              <SessionRow
                key={session.id}
                session={session}
                search={listSearch}
                onRenameRequest={setRenameTarget}
                onDeleteRequest={setDeleteTarget}
              />
            ))}
          </ul>
        ) : null}
      </WorkbenchSidebar>

      {newSessionOpen ? <NewSessionDialog onClose={() => setNewSessionOpen(false)} /> : null}
      {renameTarget ? (
        <RenameDialog session={renameTarget} onClose={() => setRenameTarget(null)} />
      ) : null}
      {deleteTarget ? (
        <DeleteDialog
          session={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => handleDeleted(deleteTarget)}
        />
      ) : null}
    </>
  )
}
