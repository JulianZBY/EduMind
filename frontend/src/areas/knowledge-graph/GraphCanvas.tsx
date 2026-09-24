import { useCallback, useMemo } from 'react'
import type { ReactNode } from 'react'
import type { GraphEdge, GraphNode } from '../../api/generated'
import { buildFlowchartSource, FlatMermaid, RelationLegend } from '../../components/graph'
import { EmptyState } from '../../components/ui'

export interface GraphCanvasProps {
  nodes: readonly GraphNode[]
  edges: readonly GraphEdge[]
  /** 选中的知识点：强调色描边（不填充色块）。 */
  selectedId: string | null
  onSelect: (nodeId: string) => void
  emptyTitle: string
  emptyDescription: string
  /** 空图时的一个出路（例如「清除过滤」）。 */
  emptyAction?: ReactNode
}

/**
 * 图谱画布：把「知识点 + 关系」交给 `buildFlowchartSource` 生成 mermaid 源码，
 * 再由 `FlatMermaid` 按扁平主题渲染（白底黑框直角节点、直角折线，四种关系用线型区分）。
 */
export function GraphCanvas({
  nodes,
  edges,
  selectedId,
  onSelect,
  emptyTitle,
  emptyDescription,
  emptyAction,
}: GraphCanvasProps) {
  const { source, nodeIdByMermaidId } = useMemo(
    () =>
      buildFlowchartSource(
        nodes.map((node) => ({
          id: node.id,
          label: node.title,
          highlighted: node.id === selectedId,
        })),
        edges.map((edge) => ({ from: edge.from, to: edge.to, relation: edge.relation_type })),
      ),
    [nodes, edges, selectedId],
  )

  const handleNodeClick = useCallback(
    (mermaidNodeId: string) => {
      const nodeId = nodeIdByMermaidId[mermaidNodeId]
      if (nodeId) onSelect(nodeId)
    },
    [nodeIdByMermaidId, onSelect],
  )

  if (nodes.length === 0) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        action={emptyAction}
      />
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <FlatMermaid
        source={source}
        onNodeClick={handleNodeClick}
        label={`知识图谱：${nodes.length} 个知识点、${edges.length} 条关系`}
        className="min-h-0 flex-1"
      />
      <div className="flex flex-wrap items-center justify-between gap-2 border-t-2 border-black px-3 py-2">
        <RelationLegend />
        <p className="text-xs text-black/60">
          {nodes.length} 个知识点 · {edges.length} 条关系 · 点节点看详情
        </p>
      </div>
    </div>
  )
}
