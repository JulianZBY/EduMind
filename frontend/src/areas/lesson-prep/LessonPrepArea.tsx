/**
 * 备课会话区（二级侧栏 = 会话列表，主区 = 对话轴）。
 *
 * 本区是教师的日常主线：发起备课、回答追问、看生成结果。全部事实源在服务端（ADR-0002）：
 * 会话列表、历史、追问粒度与参考资料都从 API 读写，浏览器侧不存会话（票 04 已把浏览器里的
 * 会话整体退场）。生成结果并排显示在对话旁（票 08 的 `GenerationPreview`），它的版本数据与
 * 生成物区同源；历史版本中心仍住生成物区。
 */
import { Link, Outlet, useParams } from 'react-router'
import { MainPanel, Workbench } from '../../components/layout/Workbench'
import { Button } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/EmptyState'
import { ConversationAxis } from './ConversationAxis'
import { GenerationPreview } from './GenerationPreview'
import { SessionSidebar } from './SessionSidebar'

export function LessonPrepArea() {
  return (
    <Workbench sidebar={<SessionSidebar />}>
      <Outlet />
    </Workbench>
  )
}

/** 主区默认内容（未选中会话时）：编辑密度，一次只做一件事。 */
export function LessonPrepIndex() {
  return (
    <MainPanel title="备课会话" tagline="一次备课的完整对话现场">
      <EmptyState
        title="还没有选中备课会话"
        description="左列是全部备课会话：新建一次备课，或选中一条继续。会话与历史存在服务端，刷新、换设备都不丢。"
        action={
          <Button asChild>
            {/* 新建走地址（`?new=1`）：URL 即状态，刷新后弹层还在，不引第二份浏览器状态 */}
            <Link to="?new=1">新建备课会话</Link>
          </Button>
        }
      />
    </MainPanel>
  )
}

/** 选中一次备课后的主区：对话轴 + 对话旁的生成结果（`/lesson-prep/:sessionId`）。*/
export function LessonPrepSession() {
  const { sessionId } = useParams()
  if (!sessionId) return <LessonPrepIndex />
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1">
      <ConversationAxis sessionId={sessionId} />
      {/* 生成结果就在对话旁：并排预览课件 / 教案 / 提纲（票 08）。对话轴行为不变。 */}
      <GenerationPreview sessionId={sessionId} />
    </div>
  )
}
