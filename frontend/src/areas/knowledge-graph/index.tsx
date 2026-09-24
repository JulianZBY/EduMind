import { KnowledgeGraphArea, KnowledgeGraphWorkbench, KNOWLEDGE_GRAPH_PATH } from './KnowledgeGraphArea'
import type { AreaModule } from '../types'

/** 知识图谱区注册：主区直铺，无二级侧栏。 */
export const knowledgeGraphArea: AreaModule = {
  id: 'knowledge-graph',
  label: '知识图谱',
  path: KNOWLEDGE_GRAPH_PATH,
  order: 40,
  tagline: '从资料里提炼出的知识点网络',
  routes: [
    {
      id: 'knowledge-graph',
      path: 'knowledge-graph',
      element: <KnowledgeGraphArea />,
      children: [
        // 「看全图」与「选中某个知识点」是同一个组件：跳转时画布不重挂，只换选中的节点
        { index: true, element: <KnowledgeGraphWorkbench /> },
        { path: ':knowledgePointId', element: <KnowledgeGraphWorkbench /> },
      ],
    },
  ],
}

export default knowledgeGraphArea
