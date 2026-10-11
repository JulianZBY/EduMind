/// <reference types="node" />
import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { GraphEdge, GraphNode } from '../../api/generated/types.gen.ts'
import {
  UNGROUPED_SUBJECT,
  applyElkLayout,
  buildGraphModel,
  buildTree,
  initialCollapsed,
  subjectRootNodeId,
  toElkGraph,
} from './graphModel.ts'

function node(id: string, subject: string | null = null): GraphNode {
  return { id, title: `知识点${id}`, subject, chapter: null, difficulty: null }
}

function contains(from: string, to: string): GraphEdge {
  return { from, to, relation_type: '父子包含' }
}

function link(from: string, to: string, relation: string): GraphEdge {
  return { from, to, relation_type: relation }
}

test('buildTree：父子包含边构成树骨架，学科根挂载孤儿节点', () => {
  const tree = buildTree(
    [node('a', '数学'), node('b', '数学'), node('c', '数学'), node('d', null)],
    [contains('a', 'b'), contains('b', 'c')],
  )
  // 数学树：a 是根挂学科根，b、c 有父
  assert.equal(tree.parentOf.get('a')?.parentId, subjectRootNodeId('数学'))
  assert.equal(tree.parentOf.get('b')?.parentId, 'a')
  assert.equal(tree.parentOf.get('c')?.parentId, 'b')
  // 无学科节点归未分类学科根
  assert.equal(tree.parentOf.get('d')?.parentId, subjectRootNodeId(UNGROUPED_SUBJECT))
  // 两个学科根
  assert.deepEqual(
    [...tree.subjectRoots.keys()].sort(),
    ['subject:数学', 'subject:未分类'].sort(),
  )
})

test('buildTree：一个孩子只留第一个父，重复的父子边降级为叠加边', () => {
  const tree = buildTree([node('a'), node('b'), node('c')], [contains('a', 'c'), contains('b', 'c')])
  assert.equal(tree.parentOf.get('c')?.parentId, 'a')
  assert.deepEqual(
    tree.demotedEdges.map((edge) => `${edge.from}>${edge.to}`),
    ['b>c'],
  )
})

test('buildTree：会成环的父子边降级，不进树骨架', () => {
  const tree = buildTree([node('a'), node('b'), node('c')], [
    contains('a', 'b'),
    contains('b', 'c'),
    contains('c', 'a'),
  ])
  assert.equal(tree.parentOf.get('b')?.parentId, 'a')
  assert.equal(tree.parentOf.get('c')?.parentId, 'b')
  assert.equal(tree.parentOf.get('a')?.parentId, subjectRootNodeId(UNGROUPED_SUBJECT)) // a 成环降级后作为根挂学科根，而不是挂 c
  assert.deepEqual(tree.demotedEdges.map((edge) => `${edge.from}>${edge.to}`), ['c>a'])
})

test('initialCollapsed：默认展开到第二层知识点（学科根为虚拟层不计入）', () => {
  // 学科根(0) → a(1) → b(2) → c(3)：知识点 a、b 两层展开，c 起折叠
  const tree = buildTree([node('a'), node('b'), node('c')], [contains('a', 'b'), contains('b', 'c')])
  const collapsed = initialCollapsed(tree)
  assert.equal(collapsed.has('a'), false)
  assert.equal(collapsed.has('b'), false)
  assert.equal(collapsed.has('c'), true)
})

test('buildTree：端点不在节点表里的父子边降级为叠加边，不进骨架（过滤后端点被滤掉的子图）', () => {
  const tree = buildTree([node('a'), node('b')], [contains('ghost', 'a'), contains('a', 'b')])
  assert.equal(tree.parentOf.get('a')?.parentId, subjectRootNodeId(UNGROUPED_SUBJECT)) // ghost 不在图里，a 回挂学科根
  assert.deepEqual(tree.demotedEdges.map((edge) => `${edge.from}>${edge.to}`), ['ghost>a'])
})

test('buildGraphModel：同向同关系的重复叠加边 id 不撞（补序号）；自环叠加边不渲染', () => {
  const tree = buildTree(
    [node('a'), node('b')],
    [link('a', 'b', '相关关联'), link('a', 'b', '相关关联'), link('a', 'a', '推导关系')],
  )
  const model = buildGraphModel(tree, new Set())
  assert.deepEqual(
    model.overlayEdges.map((edge) => edge.id),
    ['overlay:a>相关关联>b', 'overlay:a>相关关联>b#2'],
  )
})

test('buildGraphModel：折叠只藏子树，隐藏的知识点计入 hiddenCount', () => {
  const tree = buildTree([node('a'), node('b'), node('c')], [contains('a', 'b'), contains('b', 'c')])
  const model = buildGraphModel(tree, new Set(['b']))
  assert.deepEqual(
    model.nodes.map((n) => n.id),
    ['subject:未分类', 'a', 'b'],
  )
  assert.equal(model.hiddenCount, 1)
  // 树边 c 被藏，a→b 保留
  assert.equal(model.treeEdges.length, 2) // 学科根→a、a→b
})

test('buildGraphModel：叠加边一端在折叠子树里就不显示；线型按真实关系', () => {
  // 树：a ⊃ b；叠加：b–c 推导、c–d 相关、a–c 推导
  const tree = buildTree(
    [node('a'), node('b'), node('c'), node('d')],
    [contains('a', 'b'), link('b', 'c', '推导关系'), link('c', 'd', '相关关联'), link('a', 'c', '推导关系')],
  )
  const model = buildGraphModel(tree, new Set())
  assert.equal(model.overlayEdges.length, 3)
  const related = model.overlayEdges.find((edge) => edge.relation === '相关关联')
  assert.ok(related)
  assert.equal(related?.style.color, '#ff3366') // 相关关联=强调色虚线

  // 折叠 a：b 藏进子树，b 作端点的叠加边跟着消失；a 本身可见，a 作端点的边保留
  const hidden = buildGraphModel(tree, new Set(['a']))
  assert.equal(hidden.hiddenCount, 1)
  assert.deepEqual(
    hidden.overlayEdges.map((edge) => edge.id),
    ['overlay:c>相关关联>d', 'overlay:a>推导关系>c'],
  )
})

test('toElkGraph：只喂树边（叠加边绝不参与布局），带 spike 裁决的布局配置', () => {
  const tree = buildTree([node('a'), node('b')], [contains('a', 'b')])
  const model = buildGraphModel(tree, new Set())
  const elk = toElkGraph(model)
  assert.equal(elk.layoutOptions?.['elk.algorithm'], 'layered')
  assert.equal(elk.layoutOptions?.['elk.direction'], 'RIGHT')
  assert.equal(elk.children?.length, 3) // 学科根 + a + b
  assert.equal(elk.edges?.length, 2) // 只有树边
  const ids = elk.children?.map((n) => n.id)
  assert.ok(ids?.includes('subject:未分类'))
})

test('applyElkLayout：elk 结果坐标映射回节点，含负坐标平移归零', () => {
  const tree = buildTree([node('a'), node('b')], [contains('a', 'b')])
  const model = buildGraphModel(tree, new Set())
  const positioned = applyElkLayout(model, {
    id: 'root',
    children: [
      { id: 'subject:未分类', x: -30, y: -50, width: 150, height: 40 },
      { id: 'a', x: 20, y: -50, width: 150, height: 40 },
      { id: 'b', x: 170, y: -10, width: 150, height: 40 },
    ],
  })
  const byId = new Map(positioned.map((n) => [n.id, n]))
  // 全图最小 x/y 平移为非负（React Flow 画布原点在左上）
  assert.equal(Math.min(...positioned.map((n) => n.x)), 0)
  assert.equal(byId.get('a')?.x, 50) // -30 → 0，20 → 50
  assert.equal(byId.get('b')?.y, 40) // -10 → 40
})
