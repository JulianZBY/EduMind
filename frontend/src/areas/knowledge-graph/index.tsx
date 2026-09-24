import { KnowledgeGraphArea, KnowledgeGraphIndex, KnowledgeGraphNode } from './KnowledgeGraphArea'
import type { AreaModule } from '../types'

/** 知识图谱区注册：主区直铺，无二级侧栏。 */
export const knowledgeGraphArea: AreaModule = {
  id: 'knowledge-graph',
  label: '知识图谱',
  path: '/knowledge-graph',
  order: 40,
  tagline: '从资料里提炼出的知识点网络',
  routes: [
    {
      id: 'knowledge-graph',
      path: 'knowledge-graph',
      element: <KnowledgeGraphArea />,
      children: [
        { index: true, element: <KnowledgeGraphIndex /> },
        { path: ':knowledgePointId', element: <KnowledgeGraphNode /> },
      ],
    },
  ],
}

export default knowledgeGraphArea
