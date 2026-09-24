/**
 * 图谱组件出口（知识图谱区与结构冲突图示共用）。
 *
 * 复用入口：`FlatMermaid`（渲染器）+ `flowchart.ts` 里的主题 / 线型 / 源码生成。
 * 详细用法见各文件头部注释。
 */
export { FlatLoading } from './FlatLoading'
export type { FlatLoadingProps } from './FlatLoading'
export { FlatMermaid } from './FlatMermaid'
export type { FlatMermaidProps } from './FlatMermaid'
export { RelationLegend } from './RelationLegend'
export type { RelationLegendProps } from './RelationLegend'
export {
  ACCENT_COLOR,
  FLAT_THEME_INIT,
  RELATION_STYLES,
  buildFlowchartSource,
  flatThemeSource,
  mermaidNodeIdFromDomId,
  relationStyle,
  sharpenLinkCorners,
} from './flowchart'
export type {
  FlowchartEdge,
  FlowchartNode,
  FlowchartOptions,
  FlowchartSource,
  RelationStyle,
  RelationType,
} from './flowchart'
