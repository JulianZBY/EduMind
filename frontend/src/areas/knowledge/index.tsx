import { lazyAreaModule } from '../lazy'
import type { AreaModule } from '../types'

// 区实现按需加载（M6）：三个入口来自同一个 chunk，翻到本区才拉取。
const KnowledgeArea = lazyAreaModule(() => import('./KnowledgeArea'), 'KnowledgeArea')
const KnowledgeIndex = lazyAreaModule(() => import('./KnowledgeArea'), 'KnowledgeIndex')
const KnowledgeDocument = lazyAreaModule(() => import('./KnowledgeArea'), 'KnowledgeDocument')

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
