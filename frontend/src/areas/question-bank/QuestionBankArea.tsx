import { Outlet } from 'react-router'
import { MainPanel, Workbench } from '../../components/layout/Workbench'
import { EmptyState } from '../../components/ui/EmptyState'
import { QuestionDetailPanel } from './QuestionDetail'
import { QuestionList } from './QuestionList'

/** 题库区（二级侧栏 = 按考查知识点筛选的题目列表，主区 = 题目详情）。 */
export function QuestionBankArea() {
  return (
    <Workbench sidebar={<QuestionList />}>
      <MainPanel title="题库" tagline="可复用的题目资产库">
        <Outlet />
      </MainPanel>
    </Workbench>
  )
}

export function QuestionBankIndex() {
  return (
    <EmptyState
      title="还没有选中题目"
      description="左侧按考查知识点筛选题目；选中一道题，这里显示题型、答案、来源与考查知识点。"
    />
  )
}

export function QuestionBankDetail() {
  return <QuestionDetailPanel />
}
