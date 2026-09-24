import { Link, useNavigate } from 'react-router'
import { useServiceStatus } from '../api/system'
import { DEFAULT_AREA_PATH } from '../areas/registry'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/DropdownMenu'
import { ChevronDownIcon, InfoIcon, MarkerIcon } from '../components/ui/icons'
import { useToast } from '../components/ui/useToast'
import { useUiStore } from '../store/ui'

/** 顶栏：品牌入口 + 服务状态 + 关于 + 更多（下拉）。 */
export function AppHeader() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const { isPending, isError, isFetching, refetch } = useServiceStatus()
  const setAboutOpen = useUiStore((state) => state.setAboutOpen)
  const toggleRail = useUiStore((state) => state.toggleRail)

  const statusLabel = isPending ? '服务探测中' : isError ? '服务不可达' : '服务可达'

  const handleProbe = async () => {
    const result = await refetch()
    toast({
      title: result.isError ? '服务不可达' : '服务可达',
      description: '已按最新探测结果更新服务状态。',
      tone: result.isError ? 'accent' : 'default',
    })
  }

  return (
    <header className="flex flex-wrap items-center gap-3 border-b-2 border-black px-3 py-2">
      <Link
        to={DEFAULT_AREA_PATH}
        className="text-sm font-bold text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
      >
        EduMind
      </Link>
      <span className="text-xs text-black/60">多模态 AI 备课智能体</span>

      <div className="ml-auto flex flex-wrap items-center gap-2">
        <Badge
          tone={isError ? 'accent' : 'outline'}
          onClick={() => useUiStore.getState().setServicePanelOpen(true)}
          title="查看服务状态"
        >
          <MarkerIcon className={isError ? 'h-2.5 w-2.5 text-[#ff3366]' : 'h-2.5 w-2.5 text-black'} />
          {isFetching && !isPending ? `${statusLabel}（刷新中）` : statusLabel}
        </Badge>

        <Button size="sm" onClick={() => setAboutOpen(true)}>
          <InfoIcon className="h-3.5 w-3.5" />
          关于
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" aria-label="更多操作">
              更多
              <ChevronDownIcon className="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={handleProbe}>重新探测服务</DropdownMenuItem>
            <DropdownMenuItem onSelect={toggleRail}>折叠区级导航</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => navigate(DEFAULT_AREA_PATH)}>回到备课会话</DropdownMenuItem>
            <DropdownMenuItem disabled>接口文档（开发期由后端提供）</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
