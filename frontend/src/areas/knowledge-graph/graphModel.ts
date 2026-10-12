/**
 * 知识图谱画布模型：后端图数据 → React Flow 画布模型的转换纯函数。
 *
 * 核心划分（ADR-0007）：**「父子包含」边构成树骨架**（唯一参与 elk
 * 布局的边，`elk.direction='RIGHT'`）；其余三种关系与降级边是**叠加边**——只渲染、
 * 绝不参与布局（spike 实测全喂引擎会凭空多 ~500 处交叉、画布膨胀 2–4×）。
 *
 * 树骨架防御：多父（一个知识点只留第一个父）、自环、成环的「父子包含」边一律降级为
 * 叠加边——关系数据不丢，只是不给它当骨架。
 *
 * 本文件零运行时依赖（关系线型读 `flowchart.ts` 的唯一实现），可被 `node --test`
 * 直接离线运行（Node ≥ 23.6 原生 type stripping；tsconfig 已开 erasableSyntaxOnly）。
 */
import type { GraphEdge, GraphNode } from '../../api/generated/types.gen.ts'
import type { ElkNode } from 'elkjs/lib/elk-api'
import { relationStyle, type RelationStyle } from '../../components/graph/flowchart.ts'

/** 无学科知识点的归组名（CONTEXT.md：选不出归「未分类」）。 */
export const UNGROUPED_SUBJECT = '未分类'

/** 学科根（画布上的类别节点）id：加前缀防与知识点 id 碰撞。 */
export function subjectRootNodeId(subject: string): string {
  return `subject:${subject}`
}

/** 画布节点固定尺寸：单行截断，全名看详情抽屉；elk 布局也用同一份。 */
export const NODE_WIDTH = 150
export const NODE_HEIGHT = 40

/** 「父子包含」的关系名（与后端 relation_type 对齐；CONTEXT.md 第 5 节）。 */
const CONTAINS = '父子包含'

export interface TreeParent {
  readonly parentId: string
  readonly viaEdge: GraphEdge
}

export interface KnowledgeTree {
  /** 每个知识点的父节点（知识点或学科根）；键不含学科根本身。 */
  readonly parentOf: ReadonlyMap<string, TreeParent>
  /** 父 → 直接子（含学科根作父）；keys 覆盖所有「有孩子」的节点。 */
  readonly childrenOf: ReadonlyMap<string, readonly string[]>
  /** 学科根 id → 学科名。 */
  readonly subjectRoots: ReadonlyMap<string, string>
  readonly nodesById: ReadonlyMap<string, GraphNode>
  /** 树深：学科根 = 0，第一层知识点 = 1。 */
  readonly depthOf: ReadonlyMap<string, number>
  /** 降级为叠加边的「父子包含」边（多父 / 自环 / 成环）。 */
  readonly demotedEdges: readonly GraphEdge[]
  /** 其余三种关系的原始边（本就属于叠加层）。 */
  readonly relationEdges: readonly GraphEdge[]
}

/**
 * 构建树骨架：逐条吃「父子包含」边，第一个父胜出；自环、多父、会成环、
 * 端点不在节点表里的（后端过滤把父滤掉的子图）都降级为叠加边——数据不丢，
 * 只是不给它们当骨架。无父知识点挂到其学科的虚拟根（subject 为空归「未分类」）。
 */
export function buildTree(
  nodes: readonly GraphNode[],
  edges: readonly GraphEdge[],
): KnowledgeTree {
  const parentOf = new Map<string, TreeParent>()
  const demotedEdges: GraphEdge[] = []
  const relationEdges: GraphEdge[] = []
  const known = new Set(nodes.map((point) => point.id))

  /** 沿父链向上找 `candidate`：会成环则降级。 */
  const reaches = (start: string, candidate: string): boolean => {
    let current: string | undefined = start
    while (current !== undefined) {
      if (current === candidate) return true
      current = parentOf.get(current)?.parentId
    }
    return false
  }

  for (const edge of edges) {
    if (edge.relation_type !== CONTAINS) {
      relationEdges.push(edge)
      continue
    }
    const { from, to } = edge
    if (
      from === to ||
      parentOf.has(to) ||
      reaches(from, to) ||
      !known.has(from) ||
      !known.has(to)
    ) {
      demotedEdges.push(edge) // 自环 / 多父 / 成环 / 端点缺失：不给它当骨架，但数据不丢
      continue
    }
    parentOf.set(to, { parentId: from, viaEdge: edge })
  }

  const nodesById = new Map(nodes.map((point) => [point.id, point]))
  const subjectRoots = new Map<string, string>()
  for (const point of nodes) {
    const subject = point.subject ?? UNGROUPED_SUBJECT
    const rootId = subjectRootNodeId(subject)
    if (!subjectRoots.has(rootId)) subjectRoots.set(rootId, subject)
    if (!parentOf.has(point.id)) {
      parentOf.set(point.id, { parentId: rootId, viaEdge: { from: rootId, to: point.id, relation_type: CONTAINS } })
    }
  }

  const childrenOf = new Map<string, string[]>()
  for (const [child, parent] of parentOf) {
    const list = childrenOf.get(parent.parentId)
    if (list) list.push(child)
    else childrenOf.set(parent.parentId, [child])
  }

  const depthOf = new Map<string, number>()
  for (const rootId of subjectRoots.keys()) {
    depthOf.set(rootId, 0)
    const queue = [rootId]
    while (queue.length > 0) {
      const current = queue.shift() as string
      const depth = depthOf.get(current) ?? 0
      for (const child of childrenOf.get(current) ?? []) {
        depthOf.set(child, depth + 1)
        queue.push(child)
      }
    }
  }

  return { parentOf, childrenOf, subjectRoots, nodesById, depthOf, demotedEdges, relationEdges }
}

/**
 * 初始折叠集（约束「百级节点不卡死」）：默认展开到第二层**知识点**
 * （学科根是虚拟节点不算一层：知识点第 1、2 层展开，第 3 层起先折着），更深的先折着。
 */
export function initialCollapsed(tree: KnowledgeTree): ReadonlySet<string> {
  const collapsed = new Set<string>()
  for (const [id, depth] of tree.depthOf) {
    if (depth >= 3 && !tree.subjectRoots.has(id)) collapsed.add(id)
  }
  return collapsed
}

export interface CanvasNode {
  readonly id: string
  readonly label: string
  readonly kind: 'subject' | 'point'
  readonly subject: string
  /** 直接子知识点数：> 0 才显示折叠 / 展开按钮。 */
  readonly childCount: number
}

export interface CanvasEdge {
  readonly id: string
  readonly from: string
  readonly to: string
  /** 原始关系名（降级边保留「父子包含」，线型说真话）。 */
  readonly relation: string
  readonly role: 'tree' | 'overlay'
  readonly style: RelationStyle
}

export interface GraphModel {
  readonly nodes: readonly CanvasNode[]
  readonly treeEdges: readonly CanvasEdge[]
  readonly overlayEdges: readonly CanvasEdge[]
  /** 被折叠隐藏的知识点数（画布提示「还有 N 个未展开」）。 */
  readonly hiddenCount: number
}

/**
 * 应用折叠集得到可见画布模型：折叠只藏子树、不删数据；
 * 叠加边两端都可见才显示。
 */
export function buildGraphModel(tree: KnowledgeTree, collapsed: ReadonlySet<string>): GraphModel {
  const visible = new Set<string>()
  const nodes: CanvasNode[] = []
  const treeEdges: CanvasEdge[] = []
  let hiddenCount = 0

  const childrenKnowledge = (parentId: string): number =>
    (tree.childrenOf.get(parentId) ?? []).filter((id) => !tree.subjectRoots.has(id)).length

  const walk = (current: string): void => {
    visible.add(current)
    const rootSubject = tree.subjectRoots.get(current)
    if (rootSubject !== undefined) {
      nodes.push({ id: current, label: rootSubject, kind: 'subject', subject: rootSubject, childCount: childrenKnowledge(current) })
    } else {
      const point = tree.nodesById.get(current)
      nodes.push({
        id: current,
        label: point?.title ?? current,
        kind: 'point',
        subject: point?.subject ?? UNGROUPED_SUBJECT,
        childCount: childrenKnowledge(current),
      })
    }
    treeEdges.push(...treeEdgeTo(tree, current))
    if (collapsed.has(current)) {
      // 折叠：本节点可见，整棵子树隐藏（只数知识点，学科根下不会再有学科根）
      const countSubtree = (id: string): void => {
        for (const child of tree.childrenOf.get(id) ?? []) {
          hiddenCount += 1
          countSubtree(child)
        }
      }
      countSubtree(current)
      return
    }
    for (const child of tree.childrenOf.get(current) ?? []) walk(child)
  }
  for (const rootId of tree.subjectRoots.keys()) walk(rootId)

  const overlaySource = [...tree.demotedEdges, ...tree.relationEdges]
  // 同向同关系的重复边会撞 React Flow 的唯一 id 约定，重复时补序号
  const seenOverlayIds = new Map<string, number>()
  const overlayEdges = overlaySource
    .filter(
      (edge) => edge.from !== edge.to && visible.has(edge.from) && visible.has(edge.to), // 自环叠加边渲染为零长线不可见，不渲染
    )
    .map((edge) => {
      const base = `overlay:${edge.from}>${edge.relation_type}>${edge.to}`
      const nth = (seenOverlayIds.get(base) ?? 0) + 1
      seenOverlayIds.set(base, nth)
      return {
        id: nth === 1 ? base : `${base}#${nth}`,
        from: edge.from,
        to: edge.to,
        relation: edge.relation_type,
        role: 'overlay' as const,
        style: relationStyle(edge.relation_type),
      }
    })

  return { nodes, treeEdges, overlayEdges, hiddenCount }
}

/** 生成「父 → 本节点」的树边（学科根→知识点与知识点→知识点同形）。 */
function treeEdgeTo(tree: KnowledgeTree, childId: string): CanvasEdge[] {
  const parent = tree.parentOf.get(childId)
  if (!parent) return []
  return [
    {
      id: `tree:${parent.parentId}>${childId}`,
      from: parent.parentId,
      to: childId,
      relation: CONTAINS,
      role: 'tree',
      style: relationStyle(CONTAINS),
    },
  ]
}

/** elk 布局输入的最小 JSON 形状（elkjs `ELKGraph` 的手写子集，保持本文件零依赖）。 */
export interface ElkLayoutGraph {
  readonly id: string
  readonly layoutOptions?: Record<string, string>
  readonly children?: readonly { id: string; width?: number; height?: number }[]
  readonly edges?: readonly { id: string; sources: readonly [string]; targets: readonly [string] }[]
}

/** elk 布局结果的最小 JSON 形状（坐标在 `children` 上；elk 的 `ElkNode.id` 可选，这里如实放宽）。 */
export interface ElkLayoutResult {
  readonly id?: string
  readonly children?: readonly { id?: string; x?: number; y?: number; width?: number; height?: number }[]
}

/** 落地配置：layered / RIGHT / 紧凑间距；只喂树边。 */
const ELK_OPTIONS: Record<string, string> = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'spacing.nodeNode': '18',
  'spacing.betweenLayers': '64',
  'spacing.edgeNode': '10',
}

/** 画布模型 → elk 布局图（返回 elkjs 的 `ElkNode`，可直接交给 `ELK.layout`）：
 * 叠加边绝不进布局（spike 实测）。 */
export function toElkGraph(model: GraphModel): ElkNode {
  const graph: ElkLayoutGraph = {
    id: 'knowledge-graph',
    layoutOptions: ELK_OPTIONS,
    children: model.nodes.map((node) => ({ id: node.id, width: NODE_WIDTH, height: NODE_HEIGHT })),
    edges: model.treeEdges.map((edge) => ({ id: edge.id, sources: [edge.from], targets: [edge.to] })),
  }
  // SAFETY: 字段名与 elkjs 的 ElkNode/ElkExtendedEdge 逐一对齐（id/layoutOptions/children/edges、
  // sources/targets），差异仅 readonly 修饰；elk 只读不写这些数组。
  return graph as unknown as ElkNode
}

export interface PositionedCanvasNode {
  readonly id: string
  readonly x: number
  readonly y: number
}

/**
 * elk 结果 → 节点坐标：elk 允许负坐标，React Flow 画布原点在左上，故整体平移让最小 x/y ≥ 0；
 * elk 没给坐标的节点（不该发生）兜到原点，不静默丢节点。
 */
export function applyElkLayout(model: GraphModel, result: ElkLayoutResult): readonly PositionedCanvasNode[] {
  const byId = new Map<string, { x?: number; y?: number }>()
  for (const child of result.children ?? []) {
    if (child.id !== undefined) byId.set(child.id, child)
  }
  const positioned = model.nodes.map((node) => ({
    id: node.id,
    x: byId.get(node.id)?.x ?? 0,
    y: byId.get(node.id)?.y ?? 0,
  }))
  const minX = Math.min(0, ...positioned.map((node) => node.x))
  const minY = Math.min(0, ...positioned.map((node) => node.y))
  return positioned.map((node) => ({ id: node.id, x: node.x - minX, y: node.y - minY }))
}
