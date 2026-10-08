/**
 * 一条生成物时间线（某一类的全部版本）。
 *
 * 默认只展示**当前版本**；历史版本折叠在「展开历史版本」后面，需要回看、下载或
 * 以此为基线修改时才展开（CONTEXT.md「版本用语」：当前版本没有特权，只是默认打开
 * 的那一版——折叠不删除任何入口，展开后每一行仍给同样的事：回看（选中）/ 下载
 * （互动内容另有新标签页打开）/ 以此为基线修改）。
 *
 * 折叠是**纯前端交互态**：不入库、不进 URL。深链 `?v=` 指向历史版本时自动展开让选中项
 * 可见；教师点过折叠开关之后以教师的表态为准（选中的历史版本由旁边的回看列继续呈现）。
 */
import { useState } from 'react'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { ArtifactGroup, ArtifactVersion } from './queries'
import { artifactDownloadUrl } from './queries'
import { parentLabel, versionLabel } from './narrowing'

/** 互动内容取回时走 inline：浏览器直接打开试用，而不是保存文件。 */
const OPEN_IN_TAB: readonly string[] = ['互动内容']

/**
 * 折叠箭头：线宽 2 的 currentColor 线性箭头（与 `components/ui/icons` 同一画法，只在本处用，
 * 不进共享图标表）。随开关按钮黑白反色，零阴影零渐变；展开向下、折叠向右。
 */
function CollapseChevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
    >
      {expanded ? <path d="M4 6.5 8 10.5 12 6.5" /> : <path d="M6.5 4 10.5 8 6.5 12" />}
    </svg>
  )
}

export interface VersionTimelineProps {
  group: ArtifactGroup
  /** 当前回看的那一版（URL 里的 `?v=`）；为空时默认是当前版本。 */
  selectedVersionId: string | null
  onSelect: (version: ArtifactVersion) => void
  /** 以这一版为基线继续修改（一步操作：「上次那版更好，找回来」）。 */
  onReviseRequest: (version: ArtifactVersion) => void
}

/** 一行版本：回看 / 下载 / 以此为基线修改，当前版本与历史版本同一形态。 */
function VersionRow({
  version,
  group,
  selected,
  onSelect,
  onReviseRequest,
}: {
  version: ArtifactVersion
  group: ArtifactGroup
  selected: boolean
  onSelect: (version: ArtifactVersion) => void
  onReviseRequest: (version: ArtifactVersion) => void
}) {
  const isCurrent = version.id === group.current_version_id
  const derived = parentLabel(group.versions, version)
  return (
    <li className="border-b-2 border-black last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-2 px-3 py-2">
        <button
          type="button"
          aria-current={selected ? 'true' : undefined}
          onClick={() => onSelect(version)}
          className={`flex min-w-0 flex-1 flex-col gap-1 rounded-none border-l-4 px-2 py-1 text-left outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black ${
            selected ? 'border-l-[#ff3366] bg-black text-white' : 'border-l-transparent'
          }`}
        >
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold">{versionLabel(version.version)}</span>
            <Badge tone={version.origin === '修改' ? 'accent' : 'outline'}>
              {version.origin}
            </Badge>
            {isCurrent ? <Badge tone="solid">当前版本</Badge> : <Badge tone="outline">历史版本</Badge>}
          </span>
          <span className="text-xs">
            {version.created_at.slice(0, 16).replace('T', ' ')}
            {derived ? ` · ${derived}` : ''}
            {version.title ? ` · ${version.title}` : ''}
          </span>
        </button>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {selected ? <span className="text-xs text-black/60">正在回看这一版</span> : null}
          <a
            href={artifactDownloadUrl(version.id)}
            className="inline-flex h-7 items-center gap-1 rounded-none border-2 border-black bg-white px-2 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
          >
            下载文件
          </a>
          {OPEN_IN_TAB.includes(group.artifact_type) ? (
            <a
              href={artifactDownloadUrl(version.id, { openInTab: true })}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-7 items-center gap-1 rounded-none border-2 border-black bg-white px-2 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
            >
              新标签页打开
            </a>
          ) : null}
          <Button
            size="sm"
            onClick={() => onReviseRequest(version)}
            title={`以${versionLabel(version.version)}为基线继续修改`}
          >
            以此版为基线修改
          </Button>
        </div>
      </div>
    </li>
  )
}

export function VersionTimeline({ group, selectedVersionId, onSelect, onReviseRequest }: VersionTimelineProps) {
  /** 教师对折叠开关的表态；null = 还没点过（跟随深链选中项自动展开）。 */
  const [historyToggle, setHistoryToggle] = useState<boolean | null>(null)

  const current =
    group.versions.find((version) => version.id === group.current_version_id) ??
    group.versions[group.versions.length - 1]
  const history = group.versions.filter((version) => version.id !== current?.id)

  /**
   * 深链 `?v=` 指向历史版本时自动展开（否则折叠着看不见选中项）；教师点过折叠开关后，
   * 以教师的表态为准——收起就是收起，选中项由旁边的回看列继续呈现。
   */
  const selectedIsHistory = history.some((version) => version.id === selectedVersionId)
  const showHistory = historyToggle ?? selectedIsHistory

  if (!current) return null

  return (
    <section className="border-b-2 border-black">
      <header className="flex flex-wrap items-baseline gap-2 border-b-2 border-black px-3 py-2">
        <h2 className="text-sm font-bold">{group.artifact_type}</h2>
        <p className="text-xs text-black/60">
          共 {group.versions.length} 版 · 当前版本 {versionLabel(group.current_version)}
        </p>
      </header>

      <ol>
        <VersionRow
          version={current}
          group={group}
          selected={current.id === selectedVersionId}
          onSelect={onSelect}
          onReviseRequest={onReviseRequest}
        />

        {history.length > 0 ? (
          <li className="border-b-2 border-black">
            <div className="px-3 py-2">
              <button
                type="button"
                aria-expanded={showHistory}
                onClick={() => setHistoryToggle(!showHistory)}
                className="inline-flex h-7 items-center gap-1 rounded-none border-2 border-black bg-white px-2 text-xs font-bold text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
              >
                <CollapseChevron expanded={showHistory} />
                {showHistory ? '收起历史版本' : `展开历史版本（${history.length} 版）`}
              </button>
            </div>
          </li>
        ) : null}

        {showHistory
          ? history.map((version) => (
              <VersionRow
                key={version.id}
                version={version}
                group={group}
                selected={version.id === selectedVersionId}
                onSelect={onSelect}
                onReviseRequest={onReviseRequest}
              />
            ))
          : null}
      </ol>

      <p className="px-3 py-2 text-xs leading-5 text-black/60">
        默认只展示当前版本；历史版本折叠在上方入口里，需要回看、下载或以此为基线修改时再展开。
        以某一版为基线修改会产出版本号更高的新版本，原版本保持可取回。
      </p>
    </section>
  )
}
