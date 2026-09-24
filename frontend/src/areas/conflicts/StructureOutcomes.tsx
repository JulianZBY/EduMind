/**
 * 结构冲突的「图谱现状 vs 三种裁决终态」（CONTEXT.md 第 6 节 / ADR-0004 的验收项）。
 *
 * 渲染**复用知识图谱区的扁平组件**（票 10 交付）：`buildFlowchartSource` 出 mermaid 源码 +
 * `FlatMermaid` 画白底黑框直角图 + `RelationLegend` 说明四种关系的线型——
 * 与本区之外的图谱画布是同一套主题、同一种线型，不另写渲染。
 *
 * 图上画的终态由服务端按**与裁决同一套语义**算出（`structure_preview`），
 * 因此这里只负责画，不自己推算图谱会变成什么样。
 */
import type { StructureGraph, StructureOutcome } from '../../api/generated'
import { FlatMermaid, RelationLegend } from '../../components/graph'
import { Card, CardBody, CardHeader } from '../../components/ui'
import { structureGraphSource } from './structureGraph'

interface FrameProps {
  title: string
  meta?: string
  graph: StructureGraph
}

/** 一张小图：标题 + 图。空图（没有邻域）时给一句说明，不画空画布。 */
function Frame({ title, meta, graph }: FrameProps) {
  const hasGraph = graph.nodes.length > 0
  return (
    <Card>
      <CardHeader title={title} meta={meta} />
      <CardBody className="flex flex-col gap-2">
        {hasGraph ? (
          <FlatMermaid
            source={structureGraphSource(graph)}
            label={`${title}：${graph.nodes.length} 个知识点、${graph.edges.length} 条关系`}
            errorHint="可以先按「保留旧」把这条放一放；若反复画不出来，请让管理员检查知识点数据。"
          />
        ) : (
          <p className="text-xs text-black/60">这条冲突在图谱里没有邻域可画。</p>
        )}
        <p className="text-xs text-black/60">
          {graph.nodes.length} 个知识点 · {graph.edges.length} 条关系
          {graph.nodes.some((node) => node.is_new) ? ' · 新知用强调色描边' : ''}
        </p>
      </CardBody>
    </Card>
  )
}

export interface StructureOutcomesProps {
  current: StructureGraph
  outcomes: readonly StructureOutcome[]
}

export function StructureOutcomes({ current, outcomes }: StructureOutcomesProps) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-black/60">
        按下按钮之前先看清：这是冲突知识点周围的图谱现状，以及三种裁决之后它会变成什么样。
        图上的终态就是裁决后图谱的样子。
      </p>
      <div className="grid gap-3 lg:grid-cols-2">
        <Frame title="图谱现状" meta="裁决前" graph={current} />
        {outcomes.map((outcome) => (
          <Frame
            key={outcome.action}
            title={outcome.action}
            meta={`终态 ${outcome.status}`}
            graph={outcome}
          />
        ))}
      </div>
      <RelationLegend />
    </div>
  )
}
