/**
 * 题目详情：题型 / 答案 / 来源 / 考查知识点（工作台密度的数据区：贴边分隔线、一行一字段）。
 *
 * 三道状态都要符合 `docs/style/minimalist-flat.md` 第 7 节：加载中（文字 + 直角进度条）、
 * 题目不存在（强调色文案 + 回列表）、取数失败（可重试）。
 */
import type { ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { ApiError } from '../../api/client'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/EmptyState'
import { useQuestion } from './queries'
import type { QuestionDetailBody, QuestionKnowledgePoint } from './queries'

/** 来源在界面上的说法（CONTEXT.md 第 7 节：自编 / 上传 / 网络）。 */
const SOURCE_LABELS: Record<string, string> = {
  自编: '自编（AI 按备课意图生成）',
  上传: '上传（教师上传的题目）',
  网络: '网络（从网上搜来的题目）',
}

function formatCreatedAt(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (part: number) => String(part).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 border-b-2 border-black px-3 py-2">
      <dt className="w-24 shrink-0 text-xs font-bold text-black/60">{label}</dt>
      <dd className="min-w-0 flex-1 text-sm break-words whitespace-pre-wrap">{children}</dd>
    </div>
  )
}

/** 考查知识点：权重「主考」用实心标签、「涉及」用描边标签，一眼分清。 */
function KnowledgePointTags({ points }: { points: QuestionKnowledgePoint[] }) {
  if (points.length === 0) {
    return <span className="text-black/60">暂无考查知识点</span>
  }
  return (
    <span className="flex flex-wrap gap-1">
      {points.map((point) => (
        <Badge key={point.id} tone={point.weight === '主考' ? 'solid' : 'outline'}>
          {point.weight} · {point.title}
        </Badge>
      ))}
    </span>
  )
}

function QuestionDetailView({ question }: { question: QuestionDetailBody }) {
  return (
    <article>
      <section className="border-b-2 border-black px-3 py-3">
        <h2 className="mb-2 text-xs font-bold text-black/60">题干</h2>
        <p className="text-sm leading-6 whitespace-pre-wrap">{question.content}</p>
      </section>

      <dl>
        <DetailRow label="题型">{question.type}</DetailRow>
        <DetailRow label="答案">{question.answer}</DetailRow>
        <DetailRow label="来源">
          {SOURCE_LABELS[question.source_type] ?? question.source_type}
          {question.source_url ? (
            <a
              href={question.source_url}
              target="_blank"
              rel="noreferrer"
              className="ml-2 inline-flex items-center rounded-none border-2 border-black px-2 py-0.5 text-xs text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
            >
              打开来源
            </a>
          ) : null}
        </DetailRow>
        <DetailRow label="考查知识点">
          <KnowledgePointTags points={question.knowledge_points} />
        </DetailRow>
        <DetailRow label="入库时间">{formatCreatedAt(question.created_at)}</DetailRow>
      </dl>
    </article>
  )
}

export function QuestionDetailPanel() {
  const { questionId } = useParams()
  const location = useLocation()
  const { data, isPending, isError, error, refetch } = useQuestion(questionId ?? null)

  if (isPending) {
    return (
      <div className="px-3 py-3" role="status">
        <p className="text-xs">正在读取题目…</p>
        <div className="mt-2 h-1.5 w-full rounded-none border-2 border-black">
          <div className="h-full w-1/3 bg-black" />
        </div>
      </div>
    )
  }

  if (isError) {
    // 404 不是「出错」而是「这道题没了」：给出回列表的出路，别让教师对着报错发呆
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          title="题目不存在"
          description="这道题可能已被删除。回到题目列表重新选一道，或换个考查知识点再筛一遍。"
          meta={`题目：${questionId ?? ''}`}
          action={
            <Button asChild size="sm">
              {/* 带着筛选与页码回列表，上下文不丢 */}
              <Link to={{ pathname: '..', search: location.search }} relative="path">
                返回题目列表
              </Link>
            </Button>
          }
        />
      )
    }
    return (
      <EmptyState
        title="题目取不到"
        description="题库暂时取不到这道题的数据。确认后端已启动后可重试，已入库的题目不会丢。"
        action={
          <Button size="sm" onClick={() => void refetch()}>
            重试
          </Button>
        }
      />
    )
  }

  if (!data) return null
  return <QuestionDetailView question={data} />
}
