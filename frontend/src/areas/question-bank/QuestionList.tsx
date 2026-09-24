/**
 * 题库侧栏：考查知识点筛选 + 题目列表 + 翻页（工作台密度：贴边分隔线、紧凑行高）。
 *
 * 筛选与页码走 URL 搜索参数（`?knowledge_point=…&page=…`）：刷新、分享、
 * 点进详情再返回都不丢上下文（与冲突审核区同一套做法）。
 */
import { NavLink, useSearchParams } from 'react-router'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { WorkbenchSidebar } from '../../components/layout/Workbench'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { cn } from '../../lib/cn'
import { PAGE_SIZE, useQuestions } from './queries'
import type { QuestionKnowledgePoint, QuestionListBody, QuestionSummary } from './queries'

/** 页码解析：非法值一律回到第一页，手改地址不会把界面卡死。 */
function readPage(raw: string | null): number {
  const page = Number(raw ?? '1')
  return Number.isInteger(page) && page > 0 ? page : 1
}

/** 考查知识点一行文案：主考在前、涉及在后（顺序由接口保证）。 */
function knowledgePointLine(points: QuestionKnowledgePoint[]): string {
  return points.map((point) => `${point.weight} ${point.title}`).join(' · ')
}

/** 筛选按钮：选中项用强调色底（当前项标记），全部/各知识点一律可键盘操作。 */
function KnowledgePointFilter({
  points,
  active,
  onSelect,
}: {
  points: QuestionListBody['knowledge_points']
  active: string | null
  onSelect: (title: string | null) => void
}) {
  return (
    <div className="border-b-2 border-black px-3 py-2">
      <p className="mb-2 text-xs font-bold text-black/60">按考查知识点筛选</p>
      <div className="flex flex-wrap gap-1">
        <Badge tone={active ? 'outline' : 'accent'} onClick={() => onSelect(null)}>
          全部
        </Badge>
        {points.map((point) => (
          <Badge
            key={point.title}
            tone={active === point.title ? 'accent' : 'outline'}
            title={`${point.title} · ${point.question_count} 道题目`}
            onClick={() => onSelect(point.title)}
          >
            {point.title} · {point.question_count}
          </Badge>
        ))}
      </div>
    </div>
  )
}

/** 列表行：题型 / 来源 / 题干 / 考查知识点；当前行 = 黑白反色 + 强调色左边线。 */
function QuestionRow({ item }: { item: QuestionSummary }) {
  return (
    <li className="border-b-2 border-black">
      <NavLink
        to={item.id}
        className={({ isActive }) =>
          cn(
            'flex flex-col gap-1 border-l-4 px-3 py-2 outline-none transition-colors duration-150',
            'hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black',
            isActive ? 'border-l-[#ff3366] bg-black text-white' : 'border-l-transparent',
          )
        }
      >
        <div className="flex items-center gap-2">
          <Badge tone="outline">{item.type}</Badge>
          <span className="text-xs">{item.source_type}</span>
        </div>
        <p className="line-clamp-2 text-sm leading-5">{item.content}</p>
        <p className="text-xs">
          {item.knowledge_points.length > 0
            ? knowledgePointLine(item.knowledge_points)
            : '暂无考查知识点'}
        </p>
      </NavLink>
    </li>
  )
}

function Pager({
  page,
  pageCount,
  onChange,
}: {
  page: number
  pageCount: number
  onChange: (page: number) => void
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b-2 border-black px-3 py-2">
      <Button size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        上一页
      </Button>
      <span className="text-xs">
        第 {page} / {pageCount} 页
      </span>
      <Button size="sm" disabled={page >= pageCount} onClick={() => onChange(page + 1)}>
        下一页
      </Button>
    </div>
  )
}

/** 列表内的加载 / 失败 / 空态（工作台密度，主区的编辑密度空状态留给题目详情）。 */
function ListState({
  knowledgePoint,
  isPending,
  isError,
  isEmpty,
  onRetry,
}: {
  knowledgePoint: string | null
  isPending: boolean
  isError: boolean
  isEmpty: boolean
  onRetry: () => void
}) {
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
    return (
      <div className="border-b-2 border-black px-3 py-3" role="alert">
        <p className="text-xs font-bold text-[#ff3366]">题目列表加载失败</p>
        <p className="mt-1 text-xs leading-5">
          题库暂时取不到数据。确认后端已启动后可重试，已入库的题目不会丢。
        </p>
        <Button size="sm" className="mt-2" onClick={onRetry}>
          重试
        </Button>
      </div>
    )
  }
  if (!isEmpty) return null
  return (
    <SidebarNote>
      {knowledgePoint
        ? `「${knowledgePoint}」下还没有题目，换个考查知识点看看。`
        : '题库还没有题目。生成试卷后，题目会自动进入题库并标注考查知识点。'}
    </SidebarNote>
  )
}

export function QuestionList() {
  const [searchParams, setSearchParams] = useSearchParams()
  const knowledgePoint = searchParams.get('knowledge_point')
  const page = readPage(searchParams.get('page'))

  const query = {
    knowledge_point: knowledgePoint,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  }
  const { data, isPending, isError, isFetching, refetch } = useQuestions(query)

  const navigateTo = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(searchParams)
    mutate(next)
    setSearchParams(next, { replace: true })
  }

  const total = data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <WorkbenchSidebar
      title="题目列表"
      meta={data ? `${total} 道题目` : '读取中…'}
      actions={
        <Button size="sm" disabled={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
      }
    >
      {/* 筛选项来自接口回带的全量考查知识点：只有真的有题目的知识点才出现，且带题目数 */}
      {data && data.knowledge_points.length > 0 ? (
        <KnowledgePointFilter
          points={data.knowledge_points}
          active={knowledgePoint}
          onSelect={(title) =>
            navigateTo((next) => {
              if (title) next.set('knowledge_point', title)
              else next.delete('knowledge_point')
              next.delete('page') // 换筛选从第一页看起
            })
          }
        />
      ) : null}

      <ListState
        knowledgePoint={knowledgePoint}
        isPending={isPending}
        isError={isError}
        isEmpty={Boolean(data && data.items.length === 0)}
        onRetry={() => void refetch()}
      />

      {data && data.items.length > 0 ? (
        <ul>
          {data.items.map((item) => (
            <QuestionRow key={item.id} item={item} />
          ))}
        </ul>
      ) : null}

      {data && pageCount > 1 ? (
        <Pager
          page={page}
          pageCount={pageCount}
          onChange={(target) =>
            navigateTo((next) => {
              if (target <= 1) next.delete('page')
              else next.set('page', String(target))
            })
          }
        />
      ) : null}
    </WorkbenchSidebar>
  )
}
