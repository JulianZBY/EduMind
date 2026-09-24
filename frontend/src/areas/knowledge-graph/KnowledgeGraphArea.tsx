import { useCallback, useMemo } from 'react'
import { Outlet, useNavigate, useParams, useSearchParams } from 'react-router'
import { FlatLoading } from '../../components/graph'
import { MainPanel } from '../../components/layout/Workbench'
import {
  Button,
  ChevronDownIcon,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
  MarkerIcon,
} from '../../components/ui'
import { GraphCanvas } from './GraphCanvas'
import { KnowledgePointDrawer } from './KnowledgePointDrawer'
import { collectFacets, useGraph, useNeighborhood } from './queries'

/** 本区一级路由：路由注册（index.tsx）与画布内的跳转都用它，改路径只改这里。 */
export const KNOWLEDGE_GRAPH_PATH = '/knowledge-graph'

const SUBJECT_PARAM = 'subject'
const CHAPTER_PARAM = 'chapter'
const DEPTH_PARAM = 'depth'

/** 邻域跳数只认后端允许的 1–3，其余当「没在展开邻域」。 */
function readDepth(raw: string | null): number | null {
  if (raw === null) return null
  const value = Number(raw)
  return Number.isInteger(value) && value >= 1 && value <= 3 ? value : null
}

interface FilterMenuProps {
  label: string
  value: string | null
  options: readonly string[]
  onPick: (value: string | null) => void
}

/** 过滤下拉：选项来自全图；当前项用强调色方点标记（风格文档第 1 节「当前项标记」）。 */
function FilterMenu({ label, value, options, onPick }: FilterMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm">
          {label}：{value ?? '全部'}
          <ChevronDownIcon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuLabel>{label}</DropdownMenuLabel>
        {options.length === 0 ? (
          <DropdownMenuItem disabled>暂时没有可选的{label}</DropdownMenuItem>
        ) : null}
        <DropdownMenuItem onSelect={() => onPick(null)}>
          <span>全部</span>
          {value === null ? <MarkerIcon className="text-[#ff3366]" /> : null}
        </DropdownMenuItem>
        {options.map((option) => (
          <DropdownMenuItem key={option} onSelect={() => onPick(option)}>
            <span>{option}</span>
            {value === option ? <MarkerIcon className="text-[#ff3366]" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** 知识图谱区：主区直铺画布（无二级侧栏）。 */
export function KnowledgeGraphArea() {
  return (
    <MainPanel title="知识图谱" tagline="从资料里提炼出的知识点网络">
      <Outlet />
    </MainPanel>
  )
}

/**
 * 画布工作台：过滤 / 点知识点看详情 / 从选中节点展开邻域。
 *
 * 「看全图」与「选中某个知识点」是同一个组件（`index.tsx` 里两条路由都指向它），
 * 故在两者之间跳转不会重挂画布，也就不会重新渲染一遍图；
 * 视图状态全部住在 URL 上：`?subject=` / `?chapter=` 是过滤，`?depth=` 是邻域跳数，
 * 路径上的知识点 id 是选中的节点（抽屉的开合）——刷新、回退、分享链接都还原同一屏。
 */
export function KnowledgeGraphWorkbench() {
  const { knowledgePointId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const selectedId = knowledgePointId ?? null
  const subject = searchParams.get(SUBJECT_PARAM)
  const chapter = searchParams.get(CHAPTER_PARAM)
  const depth = readDepth(searchParams.get(DEPTH_PARAM))
  const neighborhoodMode = selectedId !== null && depth !== null
  const filtered = subject !== null || chapter !== null

  // 过滤选项只从全图汇总（过滤后的结果集只剩命中的取值）；不过滤时这两个查询是同一个 key
  const wholeGraph = useGraph(null, null)
  const filteredGraph = useGraph(subject, chapter)
  const neighborhood = useNeighborhood(neighborhoodMode ? selectedId : null, depth ?? 2)

  const facets = useMemo(() => collectFacets(wholeGraph.data?.nodes ?? []), [wholeGraph.data])

  const navigateTo = useCallback(
    (nodeId: string | null, nextDepth: number | null) => {
      const next = new URLSearchParams(searchParams)
      if (nextDepth === null) next.delete(DEPTH_PARAM)
      else next.set(DEPTH_PARAM, String(nextDepth))
      const path = nodeId
        ? `${KNOWLEDGE_GRAPH_PATH}/${encodeURIComponent(nodeId)}`
        : KNOWLEDGE_GRAPH_PATH
      const query = next.toString()
      navigate(query ? `${path}?${query}` : path)
    },
    [navigate, searchParams],
  )

  const setFilter = useCallback(
    (key: string, value: string | null) => {
      const next = new URLSearchParams(searchParams)
      if (value === null) next.delete(key)
      else next.set(key, value)
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  const clearFilters = useCallback(() => {
    const next = new URLSearchParams(searchParams)
    next.delete(SUBJECT_PARAM)
    next.delete(CHAPTER_PARAM)
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  const activeGraph = neighborhoodMode ? neighborhood : filteredGraph
  const nodes = activeGraph.data?.nodes ?? []
  const edges = activeGraph.data?.edges ?? []

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-black px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <FilterMenu
            label="学科"
            value={subject}
            options={facets.subjects}
            onPick={(value) => setFilter(SUBJECT_PARAM, value)}
          />
          <FilterMenu
            label="章节"
            value={chapter}
            options={facets.chapters}
            onPick={(value) => setFilter(CHAPTER_PARAM, value)}
          />
          {filtered ? (
            <Button size="sm" onClick={clearFilters}>
              清除过滤
            </Button>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-black/60">
            {neighborhoodMode
              ? `邻域子图 · 以选中的知识点为中心，向外 ${depth} 跳`
              : filtered
                ? '全图（已按学科 / 章节过滤）'
                : '全图'}
          </span>
          {neighborhoodMode ? (
            <Button size="sm" onClick={() => navigateTo(selectedId, null)}>
              返回全图
            </Button>
          ) : null}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {activeGraph.isError ? (
          <div
            role="status"
            className="m-3 rounded-none border-2 border-[#ff3366] px-3 py-2 text-sm text-black"
          >
            <p className="font-bold">图谱没读出来</p>
            <p className="mt-1 text-xs text-black/60">
              {neighborhoodMode ? '邻域子图' : '知识图谱'}接口暂时不可用，可以重试一次。
            </p>
            <Button size="sm" className="mt-2" onClick={() => void activeGraph.refetch()}>
              重试
            </Button>
          </div>
        ) : activeGraph.isPending ? (
          <FlatLoading text="正在读图谱…" />
        ) : (
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            selectedId={selectedId}
            onSelect={(nodeId) => navigateTo(nodeId, depth)}
            emptyTitle={filtered ? '这个范围里没有知识点' : '图谱还是空的'}
            emptyDescription={
              filtered
                ? '当前学科 / 章节下没有知识点。换一个范围，或者清除过滤看全部。'
                : '教学资料解析完成后，知识点与它们的关系（前置依赖 / 父子包含 / 推导关系 / 相关关联）会画在这里。'
            }
            emptyAction={
              filtered ? (
                <Button size="sm" onClick={clearFilters}>
                  清除过滤
                </Button>
              ) : undefined
            }
          />
        )}
      </div>

      <KnowledgePointDrawer
        nodeId={selectedId}
        onClose={() => navigateTo(null, null)}
        neighborhoodDepth={neighborhoodMode ? depth : null}
        onExpandNeighborhood={(nextDepth) => navigateTo(selectedId, nextDepth)}
        onShowWholeGraph={() => navigateTo(selectedId, null)}
      />
    </div>
  )
}
