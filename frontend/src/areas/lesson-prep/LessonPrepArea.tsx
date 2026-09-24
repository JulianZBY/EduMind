import { Outlet } from 'react-router'
import { AreaStub } from '../../components/layout/AreaStub'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { MainPanel, Workbench, WorkbenchSidebar } from '../../components/layout/Workbench'

/**
 * 备课会话区（二级侧栏 = 会话列表，主区 = 对话轴）。
 * 本文件是本区的界面落点：票 05/06 在这里长出会话列表与对话轴，不动路由注册（index.tsx）。
 */
export function LessonPrepArea() {
  return (
    <Workbench
      sidebar={
        <WorkbenchSidebar title="会话列表" meta="0 个会话">
          <SidebarNote>还没有备课会话。发起一次备课后，会话会出现在这里。</SidebarNote>
        </WorkbenchSidebar>
      }
    >
      <MainPanel title="备课会话" tagline="一次备课的完整对话现场">
        <Outlet />
      </MainPanel>
    </Workbench>
  )
}

/** 主区默认内容（未选中会话时）。 */
export function LessonPrepIndex() {
  return (
    <AreaStub
      title="还没有选中备课会话"
      description="左列会列出全部备课会话，选中一次备课，这里显示它的对话与生成物。"
    />
  )
}

/** 选中一次备课后可寻址的详情位（`/lesson-prep/:sessionId`）。 */
export function LessonPrepSession() {
  return (
    <AreaStub
      title="备课会话已选中"
      description="对话轴、追问粒度三档与参考资料在这里展开；当前只保证路由可寻址。"
      paramKey="sessionId"
      objectLabel="备课会话"
    />
  )
}
