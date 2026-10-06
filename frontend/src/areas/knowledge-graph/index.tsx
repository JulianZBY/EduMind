import { lazyAreaModule } from '../lazy'
import type { AreaModule } from '../types'
import { KNOWLEDGE_GRAPH_PATH } from './paths'

// 区实现按需加载（M6）：翻到本区才拉取实现 chunk（含画布那串重依赖）。
// 路径常量从 ./paths 同步取，注册表不必为此导入实现文件。
const KnowledgeGraphArea = lazyAreaModule(() => import('./KnowledgeGraphArea'), 'KnowledgeGraphArea')
const KnowledgeGraphWorkbench = lazyAreaModule(
  () => import('./KnowledgeGraphArea'),
  'KnowledgeGraphWorkbench',
)

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
