import { lazyAreaModule } from '../lazy'
import type { AreaModule } from '../types'

// 区实现按需加载（M6）：三个入口来自同一个 chunk，翻到本区才拉取。
const LessonPrepArea = lazyAreaModule(() => import('./LessonPrepArea'), 'LessonPrepArea')
const LessonPrepIndex = lazyAreaModule(() => import('./LessonPrepArea'), 'LessonPrepIndex')
const LessonPrepSession = lazyAreaModule(() => import('./LessonPrepArea'), 'LessonPrepSession')

/**
 * 备课会话区注册：导航条目（label / path / order）+ 本区路由。
 * 默认落脚区：全站唯一的 `isDefault`。
 * 路由的 `id` 与 area.id 保持一致（注册表会校验），方便排查「哪个区没挂上路由」。
 */
export const lessonPrepArea: AreaModule = {
  id: 'lesson-prep',
  label: '备课会话',
  path: '/lesson-prep',
  order: 10,
  isDefault: true,
  tagline: '一次备课的完整对话现场',
  routes: [
    {
      id: 'lesson-prep',
      path: 'lesson-prep',
      element: <LessonPrepArea />,
      children: [
        { index: true, element: <LessonPrepIndex /> },
        { path: ':sessionId', element: <LessonPrepSession /> },
      ],
    },
  ],
}

export default lessonPrepArea
