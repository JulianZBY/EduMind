import { QuestionBankArea, QuestionBankDetail, QuestionBankIndex } from './QuestionBankArea'
import type { AreaModule } from '../types'

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
