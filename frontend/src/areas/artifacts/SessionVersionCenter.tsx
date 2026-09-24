/**
 * 生成物区的版本中心：某一次备课的全部生成物时间线 + 回看某一版的列。
 *
 * 数据只有一条通路：`useSessionArtifacts`（票 07 的版本端点）——与备课会话区的并排预览
 * 用同一个 hook、同一份缓存，因此两处的版本号、当前版本、历史版本必然一致。
 * 「以此为基线修改」在时间线每一行上都是一步：选历史版本 → 填修改意见 → 产出更高版本号的新版本。
 */
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError } from '../../api/client'
import { MainPanel } from '../../components/layout/Workbench'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/EmptyState'
import { GenerateExamDialog } from './GenerateExamDialog'
import { GenerateInteractiveDialog } from './GenerateInteractiveDialog'
import { ArtifactPreview, VersionUnavailable } from './ArtifactPreview'
import { ReviseDialog } from './ReviseDialog'
import { artifactDownloadUrl, useArtifactSessions, useArtifactVersion, useSessionArtifacts } from './queries'
import type { ArtifactVersion } from './queries'
import { versionLabel, versionOf } from './narrowing'
import { VersionTimeline } from './VersionTimeline'
import { artifactsPath } from './routes'

/** 回看列：某一版的内容快照 + 这一版的下载 / 打开 / 修改入口。 */
function ReviewColumn({
  version,
  onReviseRequest,
}: {
  version: ArtifactVersion
  onReviseRequest: (version: ArtifactVersion) => void
}) {
  const detail = useArtifactVersion(version.id)
  return (
    <aside
      aria-label={`回看${version.artifact_type}${versionLabel(version.version)}`}
      className="flex w-[24rem] shrink-0 flex-col border-l-2 border-black"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-black px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-bold">{version.artifact_type}</h2>
          <Badge tone="solid">{versionLabel(version.version)}</Badge>
          <Badge tone={version.origin === '修改' ? 'accent' : 'outline'}>{version.origin}</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a
            href={artifactDownloadUrl(version.id)}
            className="inline-flex h-7 items-center gap-1 rounded-none border-2 border-black bg-white px-2 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
          >
            下载这一版
          </a>
          <Button size="sm" onClick={() => onReviseRequest(version)}>
            提修改意见
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        {detail.isPending ? (
          <div role="status" className="px-3 py-2">
            <p className="text-xs">正在读取{versionLabel(version.version)}的内容…</p>
            <div className="mt-2 h-1.5 w-full rounded-none border-2 border-black">
              <div className="h-full w-1/3 bg-black" />
            </div>
          </div>
        ) : detail.isError ? (
          <VersionUnavailable version={version} onRetry={() => void detail.refetch()} />
        ) : (
          <ArtifactPreview
            artifactType={version.artifact_type}
            content={detail.data.content}
            version={version.version}
            openInTabUrl={artifactDownloadUrl(version.id, { openInTab: true })}
          />
        )}
      </div>

      <footer className="border-t-2 border-black px-3 py-2 text-xs leading-5 text-black/60">
        {version.filename}（落盘文件名由服务端生成，同一版本固定对应这一个文件）
      </footer>
    </aside>
  )
}

/** 主区：某一次备课的版本时间线（一次没读过时是取数态，404 是「这次备课没了」）。 */
export function SessionVersionCenter({ sessionId }: { sessionId: string }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const listing = useSessionArtifacts(sessionId)
  const sessions = useArtifactSessions()
  const session = sessions.data?.sessions.find((item) => item.id === sessionId)

  const [reviseTarget, setReviseTarget] = useState<ArtifactVersion | null>(null)
  const [examOpen, setExamOpen] = useState(false)
  const [interactiveOpen, setInteractiveOpen] = useState(false)

  const selectedVersionId = searchParams.get('v')
  const groups = listing.data?.groups ?? []
  const totalVersions = groups.reduce((total, group) => total + group.versions.length, 0)

  /** 回看列显示的那一版：URL 选中的那一版；没选（或选的那一版不在列表里）就是第一条时间线的当前版本。 */
  const picked = groups
    .flatMap((group) => group.versions)
    .find((version) => version.id === selectedVersionId)
  const reviewed = picked ?? (groups[0] ? versionOf(groups[0], null) : null)

  const selectVersion = (version: ArtifactVersion) => {
    const next = new URLSearchParams(searchParams)
    next.set('v', version.id)
    setSearchParams(next, { replace: true })
  }

  const notFound = listing.error instanceof ApiError && listing.error.status === 404

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <header className="flex flex-wrap items-start justify-between gap-2 border-b-2 border-black px-3 py-2">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="text-sm font-bold">生成物</h2>
          <p className="text-xs text-black/60">
            {session?.title ?? '这次备课'} · 共 {totalVersions} 版 · 备课会话 {sessionId}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={notFound} onClick={() => setExamOpen(true)}>
            一键生成试卷
          </Button>
          <Button size="sm" disabled={notFound} onClick={() => setInteractiveOpen(true)}>
            生成互动内容
          </Button>
          <Button asChild size="sm">
            <Link to={artifactsPath}>生成物总览</Link>
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 min-w-0 flex-1 overflow-auto">
          {listing.isPending ? (
            <div role="status" className="px-3 py-3">
              <p className="text-xs">正在读取这次备课的生成物版本…</p>
              <div className="mt-2 h-1.5 w-full rounded-none border-2 border-black">
                <div className="h-full w-1/3 bg-black" />
              </div>
            </div>
          ) : listing.isError ? (
            notFound ? (
              <EmptyState
                title="备课会话不存在"
                description="这次备课可能已被删除，它的生成物版本随会话一起清掉了。回会话列表重新选一条，或到备课会话区新建一次备课。"
                meta={`备课会话：${sessionId}`}
                action={
                  <Button asChild size="sm">
                    <Link to="/lesson-prep">返回会话列表</Link>
                  </Button>
                }
              />
            ) : (
              <EmptyState
                title="生成物版本取不到"
                description="后端暂时取不回这次备课的版本列表。已入库的版本不会丢，确认后端已启动后可重试。"
                meta={`备课会话：${sessionId}`}
                action={
                  <Button size="sm" onClick={() => void listing.refetch()}>
                    重试
                  </Button>
                }
              />
            )
          ) : groups.length === 0 ? (
            <EmptyState
              title="这次备课还没有生成物"
              description="在备课会话区继续对话直到助手给出生成回复，或在这里直接一键生成试卷、按意图生成互动内容——产出都会落成这次备课的新版本。"
              meta={`备课会话：${sessionId}`}
              action={
                <>
                  <Button size="sm" onClick={() => setExamOpen(true)}>
                    一键生成试卷
                  </Button>
                  <Button size="sm" onClick={() => setInteractiveOpen(true)}>
                    生成互动内容
                  </Button>
                </>
              }
            />
          ) : (
            groups.map((group) => (
              <VersionTimeline
                key={group.artifact_type}
                group={group}
                selectedVersionId={reviewed?.id ?? null}
                onSelect={selectVersion}
                onReviseRequest={setReviseTarget}
              />
            ))
          )}
        </div>

        {reviewed ? (
          <ReviewColumn version={reviewed} onReviseRequest={setReviseTarget} />
        ) : null}
      </div>

      {reviseTarget ? (
        <ReviseDialog
          sessionId={sessionId}
          version={reviseTarget}
          onClose={() => setReviseTarget(null)}
          onRevised={(versionId) => {
            if (versionId) selectVersion({ ...reviseTarget, id: versionId })
          }}
        />
      ) : null}
      {examOpen ? (
        <GenerateExamDialog
          sessionId={sessionId}
          defaultTopic={session?.title ?? ''}
          onClose={() => setExamOpen(false)}
          onGenerated={() => setExamOpen(false)}
        />
      ) : null}
      {interactiveOpen ? (
        <GenerateInteractiveDialog
          sessionId={sessionId}
          defaultTopic={session?.title ?? ''}
          onClose={() => setInteractiveOpen(false)}
          onGenerated={() => setInteractiveOpen(false)}
        />
      ) : null}
    </section>
  )
}

/** 未选中会话时的主区（编辑密度）。 */
export function ArtifactsIndexPanel() {
  return (
    <MainPanel title="生成物" tagline="课件、教案、提纲、试卷、互动内容的版本中心">
      <EmptyState
        title="还没有选中备课会话"
        description="左列按备课会话分组列出全部生成物，每一条都写着它产出了几版。选中一条，这里显示它的版本时间线：任意历史版本都能回看、下载，也能以它为基线继续修改。"
        meta="生成物 = 一次备课产出的课件、教案、提纲、试卷、互动内容"
      />
    </MainPanel>
  )
}
