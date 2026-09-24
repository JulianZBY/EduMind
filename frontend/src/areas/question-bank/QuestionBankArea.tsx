import { Outlet } from 'react-router'
import { AreaStub } from '../../components/layout/AreaStub'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { MainPanel, Workbench, WorkbenchSidebar } from '../../components/layout/Workbench'

/** 题库区（二级侧栏 = 题目列表，主区 = 题目详情）。票 12 在此长出按考查知识点筛选。 */
export function QuestionBankArea() {
  return (
    <Workbench
      sidebar={
        <WorkbenchSidebar title="题目列表" meta="0 道题目">
          <SidebarNote>
            题库还没有题目。生成试卷后，题目会自动进入题库并标注考查知识点。
          </SidebarNote>
        </WorkbenchSidebar>
      }
    >
      <MainPanel title="题库" tagline="可复用的题目资产库">
        <Outlet />
      </MainPanel>
    </Workbench>
  )
}

export function QuestionBankIndex() {
  return (
    <AreaStub
      title="还没有选中题目"
      description="左侧按考查知识点筛选题目；选中一道题，这里显示题型、答案、解析与来源。"
    />
  )
}

export function QuestionBankDetail() {
  return (
    <AreaStub
      title="题目已选中"
      description="题干、答案、解析与考查知识点在这里展开；当前只保证路由可寻址。"
      paramKey="questionId"
      objectLabel="题目"
    />
  )
}
