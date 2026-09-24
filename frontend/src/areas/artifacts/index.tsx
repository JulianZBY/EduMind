import { ArtifactsArea, ArtifactsDetail, ArtifactsIndex } from './ArtifactsArea'
import type { AreaModule } from '../types'

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
