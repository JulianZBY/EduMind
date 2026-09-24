/**
 * 解析状态标签（皮肤与图标）：状态取值与文案口径见 `status.ts`。
 *
 * 强调色只用于「需要教师处理」的状态，且配图标与明确文案，不使用红绿蓝。
 */
import { Badge } from '../../components/ui/Badge'
import { MarkerIcon } from '../../components/ui/icons'
import { STATUS_HINT, statusTone } from './status'
import type { ParseStatus } from './status'

export function DocumentStatusBadge({ status }: { status: ParseStatus }) {
  const tone = statusTone(status)
  return (
    <Badge tone={tone} title={STATUS_HINT[status]}>
      {tone === 'accent' ? <MarkerIcon className="h-3 w-3" /> : null}
      {status}
    </Badge>
  )
}
