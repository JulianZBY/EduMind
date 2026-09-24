import { useServiceStatus } from '../api/system'
import { Button } from '../components/ui/Button'
import { Drawer } from '../components/ui/Drawer'
import { useToast } from '../components/ui/useToast'
import { useUiStore } from '../store/ui'

/**
 * 服务状态抽屉：/api/v1/ping 的现场自检。
 * 只断言「可达 / 不可达」——该端点的响应在 OpenAPI 里没有 schema，
 * 猜字段就等于手抄接口类型（ADR-0005 禁止）。
 */
export function ServiceStatusDrawer() {
  const open = useUiStore((state) => state.servicePanelOpen)
  const setOpen = useUiStore((state) => state.setServicePanelOpen)
  const { toast } = useToast()
  const { isPending, isError, isFetching, dataUpdatedAt, refetch } = useServiceStatus()

  const status = isPending ? '探测中' : isError ? '不可达' : '可达'
  const probedAt = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString('zh-CN', { hour12: false })
    : '尚未探测'

  const handleProbe = async () => {
    const result = await refetch()
    toast({
      title: result.isError ? '服务不可达' : '服务可达',
      description: '已按最新探测结果更新服务状态。',
      tone: result.isError ? 'accent' : 'default',
    })
  }

  return (
    <Drawer
      open={open}
      onOpenChange={setOpen}
      title="服务状态"
      description="后端是否可达的现场自检"
      width="max-w-sm"
    >
      <div className="flex flex-col gap-4">
        <dl className="flex flex-col rounded-none border-2 border-black">
          <div className="flex items-center justify-between gap-3 border-b-2 border-black px-3 py-2">
            <dt className="text-xs text-black/60">后端探测</dt>
            <dd className="text-sm font-bold">{status}</dd>
          </div>
          <div className="flex items-center justify-between gap-3 px-3 py-2">
            <dt className="text-xs text-black/60">最近探测</dt>
            <dd className="text-sm">{probedAt}</dd>
          </div>
        </dl>

        <p className="text-xs leading-5 text-black/60">
          后端未启动时，各区只显示空状态。stub 模式下没有云端 Key 也能全链路跑通，结果用于试用与联调。
        </p>

        <div className="flex items-center gap-2">
          <Button onClick={handleProbe} disabled={isFetching}>
            重新探测
          </Button>
          {isFetching ? <span className="text-xs text-black/60">探测中…</span> : null}
        </div>
      </div>
    </Drawer>
  )
}
