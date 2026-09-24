/**
 * 结构冲突小图 → 扁平 mermaid 源码（结构冲突图示与知识图谱区共用同一套线型与主题）。
 *
 * 复用入口就是票 10 交付的 `components/graph/flowchart.ts`：
 * `buildFlowchartSource(nodes, edges, options)` 出源码（含第 8 节的扁平主题指令、
 * 四种关系的线型、新知节点的强调色描边），交给 `FlatMermaid` 画。
 * 本模块只做「服务端的小图 → 画布输入」这一步映射，不碰渲染。
 */
import type { StructureGraph } from '../../api/generated'
import { buildFlowchartSource } from '../../components/graph'

export function structureGraphSource(graph: StructureGraph): string {
  return buildFlowchartSource(
    graph.nodes.map((node) => ({
      id: node.id,
      label: node.title || '（没有标题）',
      highlighted: node.is_new,
    })),
    graph.edges.map((edge) => ({
      from: edge.from,
      to: edge.to,
      relation: edge.relation_type,
    })),
    { direction: 'LR' },
  ).source
}
