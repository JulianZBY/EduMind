/**
 * 对话旁的生成物面板：并排预览这次备课的课件、教案、提纲，并给出下载与「提修改意见」入口。
 *
 * 边界（票 08，且不改票 06 的对话轴行为）：本面板挂在对话轴**旁边**——
 * 对话轴照旧负责澄清追问、跳过追问、进行中 / 失败可重试与生成回复里的最小入口；
 * 方向性调整的引导提示仍留在对话区，不搬到这里。本面板只管「结果」这一侧的事：
 * 并排看结果、下载、对**单个**生成物提修改意见（产出新版本）。
 *
 * 事实源与生成物区完全相同：版本数据来自 `useSessionArtifacts`（票 07 的版本端点），
 * 与生成物区的版本中心共用同一个 hook 与 query key（同一份缓存），因此两处的
 * 当前版本、历史版本必然一致——历史版本一律在生成物区按会话时间线查看。
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { ArtifactPreview, VersionUnavailable } from '../artifacts/ArtifactPreview'
import { ReviseDialog } from '../artifacts/ReviseDialog'
import { PREVIEW_TYPES, groupOfType, versionLabel, versionOf } from '../artifacts/narrowing'
import type { ArtifactGroup, ArtifactVersion } from '../artifacts/queries'
import { artifactDownloadUrl, useArtifactVersion, useSessionArtifacts } from '../artifacts/queries'
import { timelinePath } from '../artifacts/routes'

const linkBase =
  'inline-flex h-7 items-center gap-1 rounded-none border-2 border-black bg-white px-2 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black'

/** 一列预览：某一类生成物的当前版本（版本一多就指路到生成物区，不在这里铺全量历史）。 */
function PreviewColumn({
  sessionId,
  group,
  onReviseRequest,
}: {
  sessionId: string
  group: ArtifactGroup
  onReviseRequest: (version: ArtifactVersion) => void
}) {
  const current = versionOf(group, null)
  const detail = useArtifactVersion(current?.id ?? null)
  if (!current) return null

  return (
    <section
      aria-label={`${group.artifact_type}预览`}
      className="flex min-w-0 flex-1 flex-col border-l-2 border-black first:border-l-0"
    >
      <header className="flex flex-wrap items-center gap-1 border-b-2 border-black px-2 py-1">
        <h3 className="text-xs font-bold">{group.artifact_type}</h3>
        <Badge tone="outline">{versionLabel(current.version)}</Badge>
        {current.origin === '修改' ? <Badge tone="accent">修改</Badge> : null}
      </header>

      <div className="flex flex-wrap items-center gap-1 border-b-2 border-black px-2 py-1">
        <a href={artifactDownloadUrl(current.id)} className={linkBase}>
          下载{group.artifact_type}
        </a>
        <Button size="sm" onClick={() => onReviseRequest(current)}>
          提修改意见
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {detail.isPending ? (
          <div role="status" className="px-2 py-2">
            <p className="text-xs">正在读取{versionLabel(current.version)}…</p>
            <div className="mt-2 h-1.5 w-full rounded-none border-2 border-black">
              <div className="h-full w-1/3 bg-black" />
            </div>
          </div>
        ) : detail.isError ? (
          <VersionUnavailable version={current} onRetry={() => void detail.refetch()} />
        ) : (
          <ArtifactPreview
            artifactType={group.artifact_type}
            content={detail.data.content}
            version={current.version}
            openInTabUrl={artifactDownloadUrl(current.id, { openInTab: true })}
          />
        )}
      </div>

      <footer className="border-t-2 border-black px-2 py-1 text-xs text-black/60">
        {group.versions.length > 1 ? `共 ${group.versions.length} 版 · ` : ''}
        <Link
          to={timelinePath(sessionId, group.current_version_id)}
          className="font-bold text-black outline-none transition-colors duration-150 hover:text-[#ff3366] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
        >
          全部历史版本
        </Link>
      </footer>
    </section>
  )
}

/** 面板里的一行：不并排展开的类别（试卷 / 互动内容），只给当前版本与入口。 */
function CompactRow({ sessionId, group }: { sessionId: string; group: ArtifactGroup }) {
  const current = versionOf(group, null)
  if (!current) return null
  const openInTab = group.artifact_type === '互动内容'
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 border-t-2 border-black px-3 py-2">
      <span className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-bold">{group.artifact_type}</span>
        <Badge tone="outline">{versionLabel(current.version)}</Badge>
        {group.versions.length > 1 ? (
          <Link
            to={timelinePath(sessionId, current.id)}
            className="text-black/60 outline-none transition-colors duration-150 hover:text-[#ff3366] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
          >
            共 {group.versions.length} 版
          </Link>
        ) : null}
      </span>
      <span className="flex flex-wrap items-center gap-2">
        <a
          href={artifactDownloadUrl(current.id, { openInTab })}
          target="_blank"
          rel="noreferrer"
          className={linkBase}
        >
          {openInTab ? '在新标签页打开' : '下载'}
        </a>
      </span>
    </li>
  )
}

export function GenerationPreview({ sessionId }: { sessionId: string }) {
  const listing = useSessionArtifacts(sessionId)
  const [reviseTarget, setReviseTarget] = useState<ArtifactVersion | null>(null)

  const groups = listing.data?.groups ?? []
  const totalVersions = groups.reduce((total, group) => total + group.versions.length, 0)
  const previewGroups = PREVIEW_TYPES.map((type) => groupOfType(groups, type)).filter(
    (group): group is ArtifactGroup => group !== null,
  )
  const otherGroups = groups.filter((group) => !PREVIEW_TYPES.includes(group.artifact_type))

  // 这次备课还没有任何生成物：面板不占位（对话轴自己会给引导，提示不搬到这里）
  if (!listing.isPending && !listing.isError && groups.length === 0) return null

  return (
    <aside
      aria-label="这次备课的生成结果"
      className="flex w-[26rem] shrink-0 flex-col border-l-2 border-black xl:w-[32rem] 2xl:w-[38rem]"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-black px-3 py-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="text-sm font-bold">生成结果</h2>
          <p className="text-xs text-black/60">
            {listing.isPending
              ? '正在读取…'
              : listing.isError
                ? '取不到'
                : `共 ${totalVersions} 版 · 与生成物区同一份版本数据`}
          </p>
        </div>
        <Link
          to={timelinePath(sessionId)}
          className="text-xs font-bold text-black outline-none transition-colors duration-150 hover:text-[#ff3366] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
        >
          去生成物区看历史版本
        </Link>
      </header>

      {listing.isPending ? (
        <div role="status" className="px-3 py-3">
          <p className="text-xs">正在读取这次备课的生成物…</p>
          <div className="mt-2 h-1.5 w-full rounded-none border-2 border-black">
            <div className="h-full w-1/3 bg-black" />
          </div>
        </div>
      ) : listing.isError ? (
        <div className="flex flex-col items-start gap-2 px-3 py-3">
          <p className="text-xs leading-5">
            这次备课的生成物取不到：后端暂时取不回版本数据。已入库的版本不会丢。
          </p>
          <Button size="sm" onClick={() => void listing.refetch()}>
            重试
          </Button>
        </div>
      ) : (
        <>
          <div className="flex min-h-0 flex-1">
            {previewGroups.map((group) => (
              <PreviewColumn
                key={group.artifact_type}
                sessionId={sessionId}
                group={group}
                onReviseRequest={setReviseTarget}
              />
            ))}
          </div>
          {otherGroups.length > 0 ? (
            <ul className="shrink-0">
              {otherGroups.map((group) => (
                <CompactRow key={group.artifact_type} sessionId={sessionId} group={group} />
              ))}
            </ul>
          ) : null}
        </>
      )}

      {reviseTarget ? (
        <ReviseDialog
          sessionId={sessionId}
          version={reviseTarget}
          onClose={() => setReviseTarget(null)}
          onRevised={() => void listing.refetch()}
        />
      ) : null}
    </aside>
  )
}
