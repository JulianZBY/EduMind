import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import '@xyflow/react/dist/style.css'
import {
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import ELK from 'elkjs/lib/elk.bundled.js'
import type { GraphEdge, GraphNode } from '../../api/generated'
import { RelationLegend } from '../../components/graph'
import { EmptyState } from '../../components/ui'
import { cn } from '../../lib/cn'
import {
  applyElkLayout,
  buildGraphModel,
  buildTree,
  initialCollapsed,
  NODE_HEIGHT,
  NODE_WIDTH,
  toElkGraph,
  type CanvasEdge,
  type CanvasNode,
  type GraphModel,
  type PositionedCanvasNode,
} from './graphModel'

export interface GraphCanvasProps {
  nodes: readonly GraphNode[]
  edges: readonly GraphEdge[]
  /** 选中的知识点：强调色描边（不填充色块）。 */
  selectedId: string | null
  onSelect: (nodeId: string) => void
  /** 点学科根下钻进该学科子图（仅全图模式可用；下钻中传 null 禁用）。 */
  onDrillSubject: ((subject: string) => void) | null
  emptyTitle: string
  emptyDescription: string
  /** 空图时的一个出路（例如「清除过滤」）。 */
  emptyAction?: ReactNode
}

/** elk worker 实例全局一份（worker 有建线成本，画布重开不重建）。 */
let elkInstance: InstanceType<typeof ELK> | null = null
function getElk(): InstanceType<typeof ELK> {
  elkInstance ??= new ELK()
  return elkInstance
}

interface KnowledgeFlowData extends Record<string, unknown> {
  canvas: CanvasNode
  selected: boolean
  collapsed: boolean
  onToggleCollapse: (nodeId: string) => void
}

type KnowledgeFlowNode = Node<KnowledgeFlowData, 'knowledge'>

const NODE_TYPES = { knowledge: KnowledgeFlowNodeView }

/**
 * 画布节点：白底黑框直角（风格文档第 2 节），选中=强调色描边不填充（第 8 节），
 * 悬停=黑白反色（第 3 节）；学科根用标题字重区分，其余与知识点同形。
 * Handle 缩为零尺寸（只做边的锚点，不显示默认彩色圆点）。
 */
function KnowledgeFlowNodeView({ data }: NodeProps<KnowledgeFlowNode>) {
  const { canvas, selected, collapsed, onToggleCollapse } = data
  const expandable = canvas.childCount > 0
  return (
    <div
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
      className={cn(
        'flex items-stretch rounded-none border-2 bg-white transition-colors duration-150',
        selected ? 'border-[#ff3366]' : 'border-black',
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={false}
        className="!h-0 !w-0 !border-0 !bg-transparent"
      />
      <div className="flex min-w-0 flex-1 items-center justify-center px-2 hover:bg-black hover:text-white">
        <span
          className={cn('truncate text-xs', canvas.kind === 'subject' && 'font-bold')}
          title={canvas.label}
        >
          {canvas.label}
        </span>
      </div>
      {expandable ? (
        <button
          type="button"
          aria-label={collapsed ? `展开「${canvas.label}」的子知识点` : `折叠「${canvas.label}」的子知识点`}
          onClick={(event) => {
            event.stopPropagation()
            onToggleCollapse(canvas.id)
          }}
          className="flex w-6 shrink-0 items-center justify-center rounded-none border-l-2 border-black bg-white text-xs text-black transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
        >
          {collapsed ? '+' : '−'}
        </button>
      ) : null}
      <Handle
        type="source"
        position={Position.Right}
        isConnectable={false}
        className="!h-0 !w-0 !border-0 !bg-transparent"
      />
    </div>
  )
}

/** 边样式：树骨架=黑色粗实线直角折线；叠加边按真实关系线型（flowchart.ts 的唯一配方）。 */
function toFlowEdge(canvasEdge: CanvasEdge): Edge {
  const isTree = canvasEdge.role === 'tree'
  const stroke = canvasEdge.style.color
  const strokeWidth = isTree || canvasEdge.style.thick ? 3 : 2
  return {
    id: canvasEdge.id,
    source: canvasEdge.from,
    target: canvasEdge.to,
    type: isTree ? 'step' : 'straight',
    interactionWidth: 0,
    style: { stroke, strokeWidth, strokeDasharray: canvasEdge.style.dashed ? '5 3' : undefined },
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: stroke },
  }
}

/** 画布左下角「适应画布」按钮+ 布局变化后自动对齐视口。 */
function CanvasToolbar({ fitKey }: { fitKey: unknown }) {
  const { fitView } = useReactFlow()
  const firstFit = useRef(true)
  useEffect(() => {
    // 首次挂载 ReactFlow 的 fitView prop 已对齐；之后的重排（折叠/过滤）在这里补一次
    if (firstFit.current) {
      firstFit.current = false
      return
    }
    fitView({ padding: 0.15 })
  }, [fitKey, fitView])
  return (
    <button
      type="button"
      onClick={() => void fitView({ padding: 0.15 })}
      className="absolute bottom-3 left-3 z-10 rounded-none border-2 border-black bg-white px-2 py-1 text-xs text-black transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
    >
      适应画布
    </button>
  )
}

/**
 * 图谱画布（重做）：React Flow 思维导图。
 * 树骨架（父子包含）由 elk 异步分层布局（裁决：layered / RIGHT，只喂树边，
 * 叠加边绝不参与布局）；前置依赖 / 推导关系 / 相关关联以线型叠加在同一画布。
 * 滚轮缩放、拖拽平移为 React Flow 内建；节点折叠只藏子树不删数据。
 */
export function GraphCanvas({
  nodes,
  edges,
  selectedId,
  onSelect,
  onDrillSubject,
  emptyTitle,
  emptyDescription,
  emptyAction,
}: GraphCanvasProps) {
  const tree = useMemo(() => buildTree(nodes, edges), [nodes, edges])
  // 折叠是交互状态：null = 尚未交互，用「默认展开到第二层」的初始集。
  // 数据引用一换（过滤 / 邻域 / 重新拉取）就在渲染期重置（React 官方的 props 变化调 state 模式，
  // 避免 effect 里级联 setState）。
  const [view, setView] = useState<{
    data: readonly GraphNode[]
    edges: readonly GraphEdge[]
    collapsed: ReadonlySet<string> | null
  }>({ data: nodes, edges, collapsed: null })
  if (view.data !== nodes || view.edges !== edges) {
    setView({ data: nodes, edges, collapsed: null })
  }

  const initialSet = useMemo(() => initialCollapsed(tree), [tree])
  const effectiveCollapsed = view.collapsed ?? initialSet
  const model = useMemo(
    () => buildGraphModel(tree, effectiveCollapsed),
    [tree, effectiveCollapsed],
  )

  const toggleCollapse = useCallback(
    (nodeId: string) => {
      setView((previous) => {
        const base = previous.collapsed ?? initialSet
        const next = new Set(base)
        if (next.has(nodeId)) next.delete(nodeId)
        else next.add(nodeId)
        return { ...previous, collapsed: next }
      })
    },
    [initialSet],
  )

  // elk 异步布局，序号防重入（spike：mermaid 的 ELK 同款成熟模式）；
  // 布局结果与 model 绑定存放，新 model 布局完成前不回显旧坐标
  const [layout, setLayout] = useState<{
    model: GraphModel
    positions: readonly PositionedCanvasNode[]
  } | null>(null)
  const layoutSeq = useRef(0)
  useEffect(() => {
    const seq = ++layoutSeq.current
    void getElk()
      .layout(toElkGraph(model))
      .then(
        (result) => {
          if (layoutSeq.current === seq) setLayout({ model, positions: applyElkLayout(model, result) })
        },
        () => {
          // shortcut: 布局失败兜底叠原点，图仍可点可拖，只是没有层次
          if (layoutSeq.current === seq) {
            setLayout({ model, positions: model.nodes.map((node) => ({ id: node.id, x: 0, y: 0 })) })
          }
        },
      )
  }, [model])

  const positions = layout !== null && layout.model === model ? layout.positions : null
  const positionById = useMemo(
    () => new Map((positions ?? []).map((node) => [node.id, node])),
    [positions],
  )

  const flowNodes = useMemo<KnowledgeFlowNode[]>(
    () =>
      model.nodes.flatMap((node) => {
        const position = positionById.get(node.id)
        if (!position) return [] // 布局未覆盖的节点不渲染（新 model 布局完成前不回显旧图）
        return [
          {
            id: node.id,
            type: 'knowledge' as const,
            position: { x: position.x, y: position.y },
            draggable: false,
            data: {
              canvas: node,
              selected: node.id === selectedId,
              collapsed: effectiveCollapsed.has(node.id),
              onToggleCollapse: toggleCollapse,
            },
          },
        ]
      }),
    [model, positionById, selectedId, effectiveCollapsed, toggleCollapse],
  )

  const flowEdges = useMemo<Edge[]>(
    () => [...model.treeEdges, ...model.overlayEdges].map(toFlowEdge),
    [model],
  )

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: KnowledgeFlowNode) => {
      const { canvas } = node.data
      if (canvas.kind === 'subject') {
        if (onDrillSubject) onDrillSubject(canvas.subject)
        return
      }
      onSelect(canvas.id)
    },
    [onDrillSubject, onSelect],
  )

  if (nodes.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative min-h-0 flex-1 bg-white">
        {positions === null ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white">
            <p className="text-sm text-black">正在排布图谱…</p>
          </div>
        ) : (
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={NODE_TYPES}
            onNodeClick={handleNodeClick}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.1}
            maxZoom={2}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            proOptions={{ hideAttribution: false }}
            // 键盘焦点落在 React Flow 的外层包裹层（.react-flow__node 携 tabIndex），
            // 焦点环样式须挂在那里（风格 §3：可见且非浏览器默认蓝圈）
            className="rounded-none bg-white [&_.react-flow__node:focus-visible]:outline-2 [&_.react-flow__node:focus-visible]:outline-offset-2 [&_.react-flow__node:focus-visible]:outline-black"
          >
            <CanvasToolbar fitKey={positions} />
          </ReactFlow>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t-2 border-black px-3 py-2">
        <RelationLegend />
        <p className="text-xs text-black/60">
          {model.nodes.filter((node) => node.kind === 'point').length} 个知识点 ·{' '}
          {model.treeEdges.length + model.overlayEdges.length} 条关系
          {model.hiddenCount > 0 ? ` · 还有 ${model.hiddenCount} 个折叠中` : ''}
          {onDrillSubject ? ' · 点节点看详情，点学科下钻' : ' · 点节点看详情'}
        </p>
      </div>
    </div>
  )
}
