/**
 * 生成物区的二级侧栏：按备课会话分组列出全部生成物（会话列表来自服务端，计数来自版本端点）。
 *
 * 「按会话分组」是生成物区的导航结构：一次备课的全部版本挂在这次备课下面。计数走的是同一个
 * 版本端点（`GET /sessions/{id}/artifacts`），不另造统计口径，因此侧栏数字与主区时间线一致。
 */
import { useState } from 'react'
import { NavLink } from 'react-router'
import { WorkbenchSidebar } from '../../components/layout/Workbench'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { Input } from '../../components/ui/Input'
import { cn } from '../../lib/cn'
import { ARTIFACT_TYPES } from './narrowing'
import { artifactsPath, timelinePath } from './routes'
import type { SessionArtifactSummary } from './queries'
import { useArtifactSessions, useSessionArtifactSummaries } from './queries'

/** 一行的生成物口径：共几版 + 各类各几版（只列真有的类别）。 */
function artifactSummary(summary: SessionArtifactSummary | undefined): string {
  if (!summary || summary.isPending) return '正在读取生成物…'
  if (summary.isError) return '生成物取不到：切到这一条可重试'
  if (summary.totalVersions === 0) return '还没有生成物'
  return `共 ${summary.totalVersions} 版 · ${summary.groups
    .map((group) => `${group.artifact_type} ${group.versions.length} 版`)
    .join(' · ')}`
}

function SessionArtifactRow({
  sessionId,
  title,
  search,
  summary,
}: {
  sessionId: string
  title: string
  /** 选中会话时保留检索词（与服务端 `q` 同一语义）。 */
  search: string
  summary: SessionArtifactSummary | undefined
}) {
  const counts = new Map(
    (summary?.groups ?? []).map((group) => [group.artifact_type, group.versions.length]),
  )
  return (
    <li className="border-b-2 border-black">
      <NavLink
        to={{ pathname: timelinePath(sessionId), search }}
        className={({ isActive }) =>
          cn(
            'flex min-w-0 flex-col gap-1 border-l-4 px-3 py-2 outline-none transition-colors duration-150',
            'hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black',
            isActive ? 'border-l-[#ff3366] bg-black text-white' : 'border-l-transparent',
          )
        }
      >
        <span className="truncate text-sm font-bold">{title}</span>
        <span className="text-xs">{artifactSummary(summary)}</span>
        <span className="flex flex-wrap gap-1 text-xs">
          {ARTIFACT_TYPES.filter((type) => (counts.get(type) ?? 0) > 0).map((type) => (
            <span key={type} className="rounded-none border border-current px-1">
              {type} {counts.get(type)}
            </span>
          ))}
        </span>
      </NavLink>
    </li>
  )
}

export function ArtifactsSidebar() {
  const [keyword, setKeyword] = useState('')
  const [draft, setDraft] = useState('')
  const sessions = useArtifactSessions(keyword)
  const sessionIds = (sessions.data?.sessions ?? []).map((session) => session.id)
  const summaries = useSessionArtifactSummaries(sessionIds)
  const byId = new Map(summaries.map((summary) => [summary.sessionId, summary]))
  const totalVersions = summaries.reduce((total, summary) => total + summary.totalVersions, 0)
  const search = keyword ? `?${new URLSearchParams({ q: keyword }).toString()}` : ''

  return (
    <WorkbenchSidebar
      title="按会话分组"
      meta={sessions.isPending ? '正在读取…' : `生成物 ${totalVersions} 版`}
    >
      <form
        className="flex flex-wrap items-center gap-2 border-b-2 border-black px-3 py-2"
        onSubmit={(event) => {
          event.preventDefault()
          setKeyword(draft.trim())
        }}
      >
        <label htmlFor="artifacts-search" className="text-xs font-bold">
          按会话标题检索
        </label>
        <Input
          id="artifacts-search"
          value={draft}
          placeholder="输入标题后回车"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button
          type="submit"
          className="inline-flex h-7 items-center gap-1 rounded-none border-2 border-black bg-white px-2 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
        >
          检索
        </button>
        {keyword ? (
          <button
            type="button"
            onClick={() => {
              setDraft('')
              setKeyword('')
            }}
            className="inline-flex h-7 items-center gap-1 rounded-none border-2 border-black bg-white px-2 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
          >
            清空检索
          </button>
        ) : null}
      </form>

      {sessions.isPending ? (
        <SidebarNote>正在读取备课会话…</SidebarNote>
      ) : sessions.isError ? (
        <SidebarNote>
          备课会话取不到：后端暂时取不回会话列表（生成物本身不受影响）。
          <button
            type="button"
            onClick={() => void sessions.refetch()}
            className="ml-1 font-bold underline-none outline-none hover:text-[#ff3366] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
          >
            重试
          </button>
        </SidebarNote>
      ) : sessionIds.length === 0 ? (
        <SidebarNote>
          {keyword
            ? '没有标题命中这个检索词的备课会话。'
            : '还没有备课会话：先到备课会话区发起一次备课，产出会按会话分组显示在这里。'}
        </SidebarNote>
      ) : (
        <ul>
          {(sessions.data?.sessions ?? []).map((session) => (
            <SessionArtifactRow
              key={session.id}
              sessionId={session.id}
              title={session.title}
              search={search}
              summary={byId.get(session.id)}
            />
          ))}
        </ul>
      )}

      <SidebarNote>
        生成物区的起点是备课会话：选中一条会话，右侧显示它的全部生成物时间线。
        <NavLink
          to={artifactsPath}
          className="ml-1 font-bold text-black outline-none transition-colors duration-150 hover:text-[#ff3366] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
        >
          返回生成物总览
        </NavLink>
      </SidebarNote>
    </WorkbenchSidebar>
  )
}
