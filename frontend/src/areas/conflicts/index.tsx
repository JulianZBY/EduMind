import { lazyAreaModule } from '../lazy'
import type { AreaModule } from '../types'

// 区实现按需加载（M6）：三个入口来自同一个 chunk，翻到本区才拉取。
const ConflictsArea = lazyAreaModule(() => import('./ConflictsArea'), 'ConflictsArea')
const ConflictsQueue = lazyAreaModule(() => import('./ConflictsArea'), 'ConflictsQueue')
const ConflictsDetail = lazyAreaModule(() => import('./ConflictsArea'), 'ConflictsDetail')

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
