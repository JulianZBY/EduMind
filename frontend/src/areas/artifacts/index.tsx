import { lazyAreaModule } from '../lazy'
import type { AreaModule } from '../types'

// 区实现按需加载（M6）：三个入口来自同一个 chunk，翻到本区才拉取。
const ArtifactsArea = lazyAreaModule(() => import('./ArtifactsArea'), 'ArtifactsArea')
const ArtifactsIndex = lazyAreaModule(() => import('./ArtifactsArea'), 'ArtifactsIndex')
const ArtifactsDetail = lazyAreaModule(() => import('./ArtifactsArea'), 'ArtifactsDetail')

/** 生成物区注册（区名与文案照 CONTEXT.md：这个区的产出一律写「生成物」）。 */
export const artifactsArea: AreaModule = {
  id: 'artifacts',
  label: '生成物',
  path: '/artifacts',
  order: 30,
  tagline: '课件、教案、提纲、试卷、互动内容的版本中心',
  routes: [
    {
      id: 'artifacts',
      path: 'artifacts',
      element: <ArtifactsArea />,
      children: [
        { index: true, element: <ArtifactsIndex /> },
        // URL 即状态：选中哪一次备课在地址上（`?v=` 再选中回看的那一版）
        { path: ':sessionId', element: <ArtifactsDetail /> },
      ],
    },
  ],
}

export default artifactsArea
