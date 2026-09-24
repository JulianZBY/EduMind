/**
 * 生成回复里的最小结果入口：本次产出了哪几样生成物、能不能下载、命中了哪些参考资料。
 *
 * 边界（票 06）：这里只做**这一次**生成结果的最简入口——不做版本列表、不做版本时间线、
 * 不做独立生成物面板（生成物全版本留痕是票 07，版本中心是票 08）；历史版本只在文字上指路。
 */
import { Link } from 'react-router'
import { readGenerationEntries, readKnowledgeHit, readReferenceNames } from './narrowing'
import { artifactFileUrl } from './queries'

const linkBase =
  'inline-flex items-center gap-1 rounded-none border-2 border-black px-2 py-0.5 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black'

export function GeneratedResult({ artifacts }: { artifacts: unknown }) {
  const entries = readGenerationEntries(artifacts)
  const references = readReferenceNames(artifacts)
  const knowledgeHit = readKnowledgeHit(artifacts)

  if (entries.length === 0 && references.length === 0) return null

  return (
    <div className="border-t-2 border-black px-3 py-2">
      <p className="text-xs font-bold text-black/60">本次生成物</p>

      {entries.length === 0 ? (
        <p className="mt-1 text-xs leading-5">
          这次没有落地的生成物（生成环节可能失败了）：可以在对话轴里重试这一轮。
        </p>
      ) : (
        <ul className="mt-1 flex flex-wrap items-center gap-1">
          {entries.map((entry) =>
            entry.form === 'file' ? (
              <li key={`${entry.label}-${entry.filename}`}>
                <a
                  href={artifactFileUrl(entry.filename, { openInTab: entry.openInTab })}
                  target="_blank"
                  rel="noreferrer"
                  className={linkBase}
                >
                  {entry.openInTab ? `打开${entry.label}` : `下载${entry.label}`}
                </a>
              </li>
            ) : (
              <li key={entry.label} className="w-full">
                <details className="rounded-none border-2 border-black">
                  <summary className="cursor-pointer px-2 py-0.5 text-xs font-bold outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black">
                    {entry.label}（文本）
                  </summary>
                  <pre className="max-h-64 overflow-auto border-t-2 border-black px-2 py-2 text-xs whitespace-pre-wrap">
                    {entry.text}
                  </pre>
                </details>
              </li>
            ),
          )}
        </ul>
      )}

      <p className="mt-1 text-xs leading-5 text-black/60">
        {knowledgeHit === null
          ? ''
          : knowledgeHit
            ? '已融合本地知识库'
            : '知识库为空，由 AI 直接生成'}
        {references.length > 0 ? ` · 命中的参考资料：${references.join('、')}` : ''}
        {'. '}
        <Link to="/artifacts" className="underline-none font-bold outline-none transition-colors duration-150 hover:text-[#ff3366] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black">
          历史版本在生成物区查看
        </Link>
      </p>
    </div>
  )
}
