/**
 * 知识图谱区的服务端状态（TanStack Query）。
 * 约定：query key 以 `graphKeys.all` 打头，hooks 只住本文件。
 *
 * 三个端点（全部来自生成的 schema，路径不手抄）：
 * - `GET /knowledge/graph`：全图 / 按学科章节过滤后的图；
 * - `GET /knowledge/nodes/{node_id}`：节点详情；
 * - `GET /knowledge/nodes/{node_id}/neighborhood`：以选中知识点为中心的邻域子图。
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import type {
  GetGraphApiV1KnowledgeGraphGetData,
  GetGraphApiV1KnowledgeGraphGetResponse,
  GetKnowledgePointApiV1KnowledgeNodesNodeIdGetData,
  GetKnowledgePointApiV1KnowledgeNodesNodeIdGetResponse,
  GetNeighborhoodApiV1KnowledgeNodesNodeIdNeighborhoodGetData,
  GetNeighborhoodApiV1KnowledgeNodesNodeIdNeighborhoodGetResponse,
  GraphNode,
} from '../../api/generated'

export const GRAPH_URL: GetGraphApiV1KnowledgeGraphGetData['url'] = '/api/v1/knowledge/graph'
export const NODE_URL: GetKnowledgePointApiV1KnowledgeNodesNodeIdGetData['url'] =
  '/api/v1/knowledge/nodes/{node_id}'
export const NEIGHBORHOOD_URL: GetNeighborhoodApiV1KnowledgeNodesNodeIdNeighborhoodGetData['url'] =
  '/api/v1/knowledge/nodes/{node_id}/neighborhood'

export const graphKeys = {
  all: ['knowledge-graph'] as const,
  graph: (subject: string | null, chapter: string | null) =>
    [...graphKeys.all, 'graph', subject, chapter] as const,
  node: (nodeId: string) => [...graphKeys.all, 'node', nodeId] as const,
  neighborhood: (nodeId: string, maxDepth: number) =>
    [...graphKeys.all, 'neighborhood', nodeId, maxDepth] as const,
}

/** 只把有值的参数写进查询串（空串与 null 都当「不过滤」）。 */
function queryString(params: Record<string, string | number | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** 全图 / 过滤后的图：`subject`、`chapter` 传 null 即不加该过滤条件。 */
export function useGraph(subject: string | null, chapter: string | null) {
  return useQuery({
    queryKey: graphKeys.graph(subject, chapter),
    queryFn: ({ signal }) =>
      apiRequest<GetGraphApiV1KnowledgeGraphGetResponse>(
        `${GRAPH_URL}${queryString({ subject, chapter })}`,
        { signal },
      ),
    // 换过滤条件时保留上一份数据：画布不闪空，过滤选项也不会跟着缩
    placeholderData: keepPreviousData,
  })
}

/** 节点详情（节点详情抽屉）：选中知识点为空时不发请求。 */
export function useKnowledgePoint(nodeId: string | null) {
  return useQuery({
    queryKey: graphKeys.node(nodeId ?? ''),
    enabled: Boolean(nodeId),
    queryFn: ({ signal }) =>
      apiRequest<GetKnowledgePointApiV1KnowledgeNodesNodeIdGetResponse>(
        NODE_URL.replace('{node_id}', encodeURIComponent(nodeId ?? '')),
        { signal },
      ),
  })
}

/** 邻域子图：以选中知识点为中心、向外 `maxDepth` 跳。 */
export function useNeighborhood(nodeId: string | null, maxDepth: number) {
  return useQuery({
    queryKey: graphKeys.neighborhood(nodeId ?? '', maxDepth),
    enabled: Boolean(nodeId),
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) =>
      apiRequest<GetNeighborhoodApiV1KnowledgeNodesNodeIdNeighborhoodGetResponse>(
        `${NEIGHBORHOOD_URL.replace('{node_id}', encodeURIComponent(nodeId ?? ''))}${queryString({
          max_depth: maxDepth,
        })}`,
        { signal },
      ),
  })
}

export interface GraphFacets {
  subjects: string[]
  chapters: string[]
}

/**
 * 过滤选项（学科 / 章节）只从**全图**节点汇总：
 * 过滤后的结果集只剩命中的取值，拿它当选项就再也回不到别的学科了。
 */
export function collectFacets(nodes: readonly GraphNode[]): GraphFacets {
  const subjects = new Set<string>()
  const chapters = new Set<string>()
  for (const node of nodes) {
    if (node.subject) subjects.add(node.subject)
    if (node.chapter) chapters.add(node.chapter)
  }
  return {
    subjects: [...subjects].sort((a, b) => a.localeCompare(b)),
    chapters: [...chapters].sort((a, b) => a.localeCompare(b)),
  }
}
