/**
 * 二级侧栏：教学资料列表（工作台密度——紧凑行高、贴边分隔线、一屏尽量多信息）。
 *
 * 行内两件事：进详情（整行是链接）与切换参考资料标记（独立按钮，避免嵌套交互元素）。
 * 参考资料标记走乐观更新（`useSetDocumentReference`），点下去立刻变，失败再回滚。
 */
import { NavLink } from 'react-router'
import type { DocumentView } from '../../api/generated'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/useToast'
import { cn } from '../../lib/cn'
import { DocumentStatusBadge } from './DocumentStatus'
import { documentErrorMessage, useSetDocumentReference } from './queries'

export interface DocumentsSidebarProps {
  documents: readonly DocumentView[]
  isPending: boolean
  isError: boolean
}

export function DocumentsSidebar({ documents, isPending, isError }: DocumentsSidebarProps) {
  if (isPending) return <SidebarNote>正在读取资料列表…</SidebarNote>
  if (isError) return <SidebarNote>资料列表没有读出来；可在右侧重试。</SidebarNote>
  if (documents.length === 0) {
    return (
      <SidebarNote>
        还没有教学资料。点右上角「上传资料」选一个文件：PDF、Word、PPT、图片、视频、录音都能解析。
      </SidebarNote>
    )
  }

  return (
    <ul className="flex flex-col">
      {documents.map((document) => (
        <DocumentRow key={document.id} document={document} />
      ))}
    </ul>
  )
}

function DocumentRow({ document }: { document: DocumentView }) {
  const setReference = useSetDocumentReference()
  const { toast } = useToast()
  const marked = document.is_reference

  function toggleReference() {
    setReference.mutate(
      { documentId: document.id, isReference: !marked },
      {
        onError: (error) => {
          toast({
            title: '参考资料标记没有切换成功',
            description: documentErrorMessage(error),
            tone: 'accent',
          })
        },
      },
    )
  }

  return (
    <li className="flex items-stretch border-b-2 border-black">
      <NavLink
        to={document.id}
        className={({ isActive }) =>
          cn(
            'flex min-w-0 flex-1 flex-col gap-1 px-3 py-2 text-sm outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black',
            isActive && 'bg-black text-white',
          )
        }
      >
        <span className="truncate font-bold">{document.filename}</span>
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <DocumentStatusBadge status={document.status} />
          <span className="uppercase">{document.file_type}</span>
        </span>
      </NavLink>
      <div className="flex shrink-0 items-center py-1 pr-2">
        <Button
          size="sm"
          variant={marked ? 'accent' : 'default'}
          aria-pressed={marked}
          disabled={setReference.isPending}
          title={
            marked
              ? '已标记为参考资料：备课检索会加权，生成物里会溯源到这份资料。点击取消标记。'
              : '标记为参考资料：备课时检索会加权，生成物里会溯源到这份资料。'
          }
          onClick={toggleReference}
        >
          参考资料
        </Button>
      </div>
    </li>
  )
}
