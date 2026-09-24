import { Link } from 'react-router'
import { DEFAULT_AREA_PATH } from '../areas/registry'
import { Button } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'

/** 兜底页：未知地址落到这里，编辑密度，一次只做一件事——回到备课会话。 */
export function NotFoundPage() {
  return (
    <div className="flex min-h-0 flex-1 items-start justify-center">
      <EmptyState
        title="这个地址不存在"
        description="工作台只有六个区与设置。回到备课会话，继续今天那节课。"
        action={
          <Button asChild>
            <Link to={DEFAULT_AREA_PATH}>回到备课会话</Link>
          </Button>
        }
      />
    </div>
  )
}
