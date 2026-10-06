import { lazyAreaModule } from '../lazy'
import type { AreaModule } from '../types'

// 区实现按需加载（M6）：三个入口来自同一个 chunk，翻到本区才拉取。
const QuestionBankArea = lazyAreaModule(() => import('./QuestionBankArea'), 'QuestionBankArea')
const QuestionBankIndex = lazyAreaModule(() => import('./QuestionBankArea'), 'QuestionBankIndex')
const QuestionBankDetail = lazyAreaModule(() => import('./QuestionBankArea'), 'QuestionBankDetail')

/** 题库区注册。 */
export const questionBankArea: AreaModule = {
  id: 'question-bank',
  label: '题库',
  path: '/question-bank',
  order: 60,
  tagline: '可复用的题目资产库',
  routes: [
    {
      id: 'question-bank',
      path: 'question-bank',
      element: <QuestionBankArea />,
      children: [
        { index: true, element: <QuestionBankIndex /> },
        { path: ':questionId', element: <QuestionBankDetail /> },
      ],
    },
  ],
}

export default questionBankArea
