/**
 * 二级侧栏 = 备课会话列表：新建 / inline 改名 / 删除 / 检索，全部与服务端状态同步。
 *
 * 浏览器里没有会话事实：列表来自 `GET /api/v1/sessions`（检索走后端的标题过滤 `q=`），
 * 增删改都打到服务端再让 Query 失效重取。新建是零表单直开（票 04）：点「新建备课会话」
 * 直接 POST 后进会话，不再弹层；改名是行内 inline 编辑，同样不弹层。
 * 本区不得再引入任何浏览器侧的会话事实源。
 */
import { useRef, useState } from 'react'
import { NavLink, useNavigate, useParams, useSearchParams } from 'react-router'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { WorkbenchSidebar } from '../../components/layout/Workbench'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../../components/ui/DropdownMenu'
import { Input } from '../../components/ui/Input'
import { useToast } from '../../components/ui/useToast'
import { cn } from '../../lib/cn'
import { SessionRenameForm } from './SessionRenameForm'
import { formatTimestamp } from './format'
import type { SessionSummary } from './queries'
import {
  useCreateAndOpenSession,
  useDeleteSession,
  useSessions,
} from './queries'
import { LESSON_PREP_PATH, sessionPath } from './routes'

/** 检索输入停顿多久后才落到地址上（地址即检索条件，但不逐键改 URL）。 */
const SEARCH_DEBOUNCE_MS = 250

/** 一行会话：一体式条目——整行是同一个矩形（没有左信息 / 右操作的竖线分割），选中时整行黑白反色。 */
function SessionRow({
  session,
  search,
  active,
  renaming,
  onRenameRequest,
  onRenameDone,
  onDeleteRequest,
}: {
  session: SessionSummary
  /** 选中会话时保留的检索条件（进会话不丢筛选，与题库区同一口径）。 */
  search: string
  /** 这条是否是当前打开的会话：整行反色，而不是只反色左侧链接。 */
  active: boolean
  /** 这条是否正在 inline 改名：行内容换成改名表单（票 04：改名不弹层）。 */
  renaming: boolean
  onRenameRequest: (session: SessionSummary) => void
  onRenameDone: () => void
  onDeleteRequest: (session: SessionSummary) => void
}) {
  if (renaming) {
    return (
      <li className="border-b-2 border-black bg-white px-2 py-2 text-black">
        <SessionRenameForm session={session} onDone={onRenameDone} />
      </li>
    )
  }
  return (
    <li
      className={cn(
        'border-b-2 border-black transition-colors duration-150',
        active ? 'bg-black text-white' : 'bg-white text-black',
      )}
    >
      <div className="flex items-stretch">
        <NavLink
          to={{ pathname: sessionPath(session.id), search }}
          className={({ isActive }) =>
            cn(
              'flex min-w-0 flex-1 flex-col gap-1 border-l-4 px-3 py-2 outline-none transition-colors duration-150',
              'hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black',
              isActive ? 'border-l-[#ff3366]' : 'border-l-transparent',
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
        <div className="flex shrink-0 items-center px-1">
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
  /** 正在 inline 改名的会话 id（行内表单，不弹层；保存/取消后回 null）。 */
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<SessionSummary | null>(null)
  const debounce = useRef<number | null>(null)
  const newSession = useCreateAndOpenSession()

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
          <Button size="sm" disabled={newSession.creating} onClick={newSession.openNewSession}>
            {newSession.creating ? '正在新建…' : '新建备课会话'}
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

        {newSession.failed ? (
          <div className="border-b-2 border-black px-3 py-2" role="alert">
            <p className="text-xs font-bold text-[#ff3366]">新建备课会话没成功</p>
            <p className="mt-1 text-xs leading-5">
              后端暂时取不到会话。确认后端已启动后，再点一次「新建备课会话」。
            </p>
          </div>
        ) : null}

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
                active={session.id === currentSessionId}
                renaming={session.id === renamingId}
                onRenameRequest={(target) => setRenamingId(target.id)}
                onRenameDone={() => setRenamingId(null)}
                onDeleteRequest={setDeleteTarget}
              />
            ))}
          </ul>
        ) : null}
      </WorkbenchSidebar>

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
