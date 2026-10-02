/**
 * 未配置供应商的引导条：产品没有假数据兜底——云端能力没配置时，相关操作返回 503
 * （`code: provider_not_configured`，message 指向设置页）。各区在「要动用云端能力」的
 * 入口放这条引导，让教师先看到去哪配，而不是等操作失败才撞上错误。
 *
 * 宿主用法（数据源 hook 在 `./queries`）：
 *   const missing = useProviderMissingState()
 *   {missing.providersMissing ? <ProviderMissingNotice message="…" /> : null}
 */
import { useNavigate } from 'react-router'
import { Button } from '../../components/ui/Button'

export function ProviderMissingNotice({ message }: { message: string }) {
  const navigate = useNavigate()
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-none border-2 border-black bg-white px-3 py-2">
      <p className="min-w-0 flex-1 text-xs font-bold leading-5">{message}</p>
      <Button size="sm" onClick={() => navigate('/settings')}>
        去设置
      </Button>
    </div>
  )
}
