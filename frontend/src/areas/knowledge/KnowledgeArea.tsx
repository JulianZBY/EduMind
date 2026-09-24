import { Outlet } from 'react-router'
import { AreaStub } from '../../components/layout/AreaStub'
import { SidebarNote } from '../../components/layout/SidebarNote'
import { MainPanel, Workbench, WorkbenchSidebar } from '../../components/layout/Workbench'

/** 知识库区（二级侧栏 = 资料列表，主区 = 资料详情）。票 09 在此长出上传与状态跟进。 */
export function KnowledgeArea() {
  return (
    <Workbench
      sidebar={
        <WorkbenchSidebar title="资料列表" meta="0 份资料">
          <SidebarNote>
            还没有教学资料。上传 PDF、Word、PPT、图片、视频或录音后，解析状态会显示在这里。
          </SidebarNote>
        </WorkbenchSidebar>
      }
    >
      <MainPanel title="知识库" tagline="教师个人教学资料的仓库">
        <Outlet />
      </MainPanel>
    </Workbench>
  )
}

export function KnowledgeIndex() {
  return (
    <AreaStub
      title="还没有选中教学资料"
      description="左列按解析状态跟进每一份资料；选中一份资料，这里显示分块与来源。"
    />
  )
}

export function KnowledgeDocument() {
  return (
    <AreaStub
      title="教学资料已选中"
      description="解析状态、分块与参考资料标记在这里查看；当前只保证路由可寻址。"
      paramKey="documentId"
      objectLabel="教学资料"
    />
  )
}
