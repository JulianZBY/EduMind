/**
 * 生成回复里的最小结果入口：本次产出了哪几样生成物、能不能下载、命中了哪些参考资料。
 *
 * 边界（票 06）：这里只做**这一次**生成结果的最简入口——不做版本列表、不做版本时间线、
 * 不做独立生成物面板（生成物全版本留痕是票 07，版本中心是票 08）；历史版本只在文字上指路。
 */
import { Link } from 'react-router'
import {
  readGenerationEntries,
  readKnowledgeOutcome,
  readReferenceNames,
  readWebSearchQuery,
} from './narrowing'
import { artifactFileUrl, useWebSearchIngest } from './queries'
import { Button } from '../../components/ui/Button'
import { ApiError, apiErrorMessage } from '../../api/client'

const linkBase =
  'inline-flex items-center gap-1 rounded-none border-2 border-black px-2 py-0.5 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black'

export function GeneratedResult({ artifacts }: { artifacts: unknown }) {
  const entries = readGenerationEntries(artifacts)
  const references = readReferenceNames(artifacts)
  const knowledgeOutcome = readKnowledgeOutcome(artifacts)

  const canIngest = knowledgeOutcome === 'empty' || knowledgeOutcome === 'no_match'

  if (entries.length === 0 && references.length === 0 && !canIngest) return null

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
        {/* 知识库口径按后端语义显示（票 01）：命中 / 未命中相关内容 / 库为空，各说各话 */}
        {knowledgeOutcome === null
          ? ''
          : knowledgeOutcome === 'hit'
            ? '已融合本地知识库'
            : knowledgeOutcome === 'empty'
              ? '知识库为空，由 AI 直接生成'
              : '知识库未命中相关内容，由 AI 直接生成'}
        {references.length > 0 ? ` · 命中的参考资料：${references.join('、')}` : ''}
        {'。'}
        <Link to="/artifacts" className="underline-none font-bold outline-none transition-colors duration-150 hover:text-[#ff3366] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black">
          历史版本在生成物区查看
        </Link>
      </p>
      {canIngest ? (
        <WebSearchIngestAction query={readWebSearchQuery(artifacts)} />
      ) : null}
    </div>
  )
}

/** 空库与非空库无相关命中均可手动入库；进行中、失败、已接收各自如实反馈。 */
function WebSearchIngestAction({ query }: { query: string | null }) {
  const ingest = useWebSearchIngest()
  const needsSettings = ingest.error instanceof ApiError && ingest.error.status === 503

  return (
    <div className="mt-2 rounded-none border-2 border-black px-2 py-2">
      <Button
        size="sm"
        disabled={!query || ingest.isPending || ingest.isSuccess}
        onClick={() => {
          if (query) ingest.mutate({ query })
        }}
      >
        联网检索并入库
      </Button>
      <p className="mt-1 text-xs leading-5 text-black/60">
        仅在你点击后检索。结果进入知识库，不改变本次课件；后续备课经知识库检索使用。
      </p>
      {!query ? <p className="text-xs leading-5">这条记录没有备课主题，请在新的生成回复中发起联网检索并入库。</p> : null}
      {ingest.isPending ? (
        <p role="status" className="mt-1 text-xs leading-5">
          联网检索并入库进行中：正在检索并接收入库，请稍候。
        </p>
      ) : null}
      {ingest.isSuccess ? (
        <p role="status" className="mt-1 text-xs leading-5">
          {ingest.data.ingested === 0
            ? '联网检索并入库未找到结果，知识库没有新增资料。'
            : `联网检索并入库已接收 ${ingest.data.ingested} 份网页资料，正在后台处理。请到知识库查看文献笔记与处理结果；有矛盾的知识点进入冲突审核，待审时不入知识图谱。`}
          <Link to="/knowledge" className={linkBase}>查看知识库</Link>
        </p>
      ) : null}
      {ingest.isError ? (
        <p role="alert" className="mt-1 text-xs leading-5 text-[#ff3366]">
          {apiErrorMessage(ingest.error, '联网检索并入库没有成功，请稍后重试。')}
          {needsSettings ? <Link to="/settings" className={linkBase}>去设置页配置</Link> : null}
        </p>
      ) : null}
    </div>
  )
}
