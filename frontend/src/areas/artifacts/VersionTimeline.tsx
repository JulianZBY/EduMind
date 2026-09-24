/**
 * 一条生成物时间线（某一类的全部版本）。
 *
 * CONTEXT.md 的「版本用语」是硬约束：**当前版本没有特权**，它只是默认打开的那一版；
 * 历史版本一律可回看、可下载、可作基线继续修改。因此每一行都给同样的四件事：
 * 回看（选中）/ 下载（互动内容另有新标签页打开）/ 以此为基线修改，只在「当前版本」上多一个标注。
 */
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { ArtifactGroup, ArtifactVersion } from './queries'
import { artifactDownloadUrl } from './queries'
import { parentLabel, versionLabel } from './narrowing'

/** 互动内容取回时走 inline：浏览器直接打开试用，而不是保存文件。 */
const OPEN_IN_TAB: readonly string[] = ['互动内容']

export interface VersionTimelineProps {
  group: ArtifactGroup
  /** 当前回看的那一版（URL 里的 `?v=`）；为空时默认是当前版本。 */
  selectedVersionId: string | null
  onSelect: (version: ArtifactVersion) => void
  /** 以这一版为基线继续修改（一步操作：「上次那版更好，找回来」）。 */
  onReviseRequest: (version: ArtifactVersion) => void
}

export function VersionTimeline({ group, selectedVersionId, onSelect, onReviseRequest }: VersionTimelineProps) {
  return (
    <section className="border-b-2 border-black">
      <header className="flex flex-wrap items-baseline gap-2 border-b-2 border-black px-3 py-2">
        <h2 className="text-sm font-bold">{group.artifact_type}</h2>
        <p className="text-xs text-black/60">
          共 {group.versions.length} 版 · 当前版本 {versionLabel(group.current_version)}
        </p>
      </header>

      <ol>
        {group.versions.map((version) => {
          const selected = version.id === selectedVersionId
          const isCurrent = version.id === group.current_version_id
          const derived = parentLabel(group.versions, version)
          return (
            <li key={version.id} className="border-b-2 border-black last:border-b-0">
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
        })}
      </ol>

      <p className="px-3 py-2 text-xs leading-5 text-black/60">
        历史版本与当前版本一样可回看、可下载、可作基线；以某一版为基线修改会产出版本号更高的新版本，
        原版本保持可取回。
      </p>
    </section>
  )
}
