import { ConflictsArea, ConflictsDetail, ConflictsQueue } from './ConflictsArea'
import type { AreaModule } from '../types'

/** 冲突审核区注册：主区直铺队列，类别走搜索参数。 */
export const conflictsArea: AreaModule = {
  id: 'conflicts',
  label: '冲突审核',
  path: '/conflicts',
  order: 50,
  tagline: '新知识进库前，教师裁决矛盾的地方',
  routes: [
    {
      id: 'conflicts',
      path: 'conflicts',
      element: <ConflictsArea />,
      children: [
        { index: true, element: <ConflictsQueue /> },
        { path: ':conflictId', element: <ConflictsDetail /> },
      ],
    },
  ],
}

export default conflictsArea
