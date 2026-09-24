import { Outlet } from 'react-router'
import { AreaStub } from '../../components/layout/AreaStub'
import { MainPanel } from '../../components/layout/Workbench'

/** 知识图谱区：主区直铺画布（票 10 在此按扁平主题渲染 mermaid 图谱）。 */
export function KnowledgeGraphArea() {
  return (
    <MainPanel title="知识图谱" tagline="从资料里提炼出的知识点网络">
      <Outlet />
    </MainPanel>
  )
}

export function KnowledgeGraphIndex() {
  return (
    <AreaStub
      title="图谱还是空的"
      description="教学资料解析完成后，知识点与它们的关系（前置依赖 / 父子包含 / 推导关系 / 相关关联）会画在这里。"
    />
  )
}

export function KnowledgeGraphNode() {
  return (
    <AreaStub
      title="知识点已选中"
      description="节点详情（内容 / 难度 / 来源引用）与邻域子图在这里展开；当前只保证路由可寻址。"
      paramKey="knowledgePointId"
      objectLabel="知识点"
    />
  )
}
