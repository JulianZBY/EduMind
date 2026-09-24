import { KnowledgeArea, KnowledgeDocument, KnowledgeIndex } from './KnowledgeArea'
import type { AreaModule } from '../types'

/** 知识库区注册。 */
export const knowledgeArea: AreaModule = {
  id: 'knowledge',
  label: '知识库',
  path: '/knowledge',
  order: 20,
  tagline: '教师个人教学资料的仓库',
  routes: [
    {
      id: 'knowledge',
      path: 'knowledge',
      element: <KnowledgeArea />,
      children: [
        { index: true, element: <KnowledgeIndex /> },
        { path: ':documentId', element: <KnowledgeDocument /> },
      ],
    },
  ],
}

export default knowledgeArea
