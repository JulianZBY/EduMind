import { Outlet, useParams } from 'react-router'
import { Workbench } from '../../components/layout/Workbench'
import { ArtifactsSidebar } from './ArtifactsSidebar'
import { ArtifactsIndexPanel, SessionVersionCenter } from './SessionVersionCenter'

/** 生成物区（二级侧栏 = 按会话分组，主区 = 版本中心）。 */
export function ArtifactsArea() {
  return (
    <Workbench sidebar={<ArtifactsSidebar />}>
      <Outlet />
    </Workbench>
  )
}

/** 未选中会话时的主区：这一区的起点是选一条备课会话。 */
export function ArtifactsIndex() {
  return <ArtifactsIndexPanel />
}

/** 选中一次备课后的主区：它的全部生成物版本时间线（`/artifacts/:sessionId`）。 */
export function ArtifactsDetail() {
  const { sessionId } = useParams()
  if (!sessionId) return <ArtifactsIndexPanel />
  return <SessionVersionCenter sessionId={sessionId} />
}
