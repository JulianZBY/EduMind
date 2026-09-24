import { Outlet } from 'react-router'
import { AreaStub } from '../../components/layout/AreaStub'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { MainPanel, Workbench, WorkbenchSidebar } from '../../components/layout/Workbench'

/** 生成物区（二级侧栏 = 按会话分组，主区 = 版本中心）。票 07/08 在此长出预览与历史版本。 */
export function ArtifactsArea() {
  return (
    <Workbench
      sidebar={
        <WorkbenchSidebar title="按会话分组" meta="0 个生成物">
          <SidebarNote>
            还没有生成物。备课会话里产出课件、教案、提纲、试卷或互动内容后，按会话分组显示在这里。
          </SidebarNote>
        </WorkbenchSidebar>
      }
    >
      <MainPanel title="生成物" tagline="课件、教案、提纲、试卷、互动内容的版本中心">
        <Outlet />
      </MainPanel>
    </Workbench>
  )
}

export function ArtifactsIndex() {
  return (
    <AreaStub
      title="还没有选中生成物"
      description="左侧按备课会话分组列出全部生成物；选中一个生成物，这里显示它的全部历史版本。"
    />
  )
}

export function ArtifactsDetail() {
  return (
    <AreaStub
      title="生成物已选中"
      description="预览、下载、修改意见与历史版本在这里展开；当前只保证路由可寻址。"
      paramKey="artifactId"
      objectLabel="生成物"
    />
  )
}
