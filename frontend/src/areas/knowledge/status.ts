/**
 * 解析状态的口径与文案（CONTEXT.md 第 4 节：处理中 → 已完成 / 有冲突 / 失败）。
 *
 * 这里是纯数据与纯函数（无 JSX）：状态取值来自生成的 schema，判断与文案单点可查，
 * 标签皮肤单独放 `DocumentStatus.tsx`（组件文件只导出组件，Fast Refresh 才不会被打断）。
 *
 * 风格纪律（docs/style/minimalist-flat.md 第 1 节）：状态不用红绿蓝，
 * 「需要教师处理」的两种状态用强调色 + 图标 + 明确文案表达。
 */
import type { BadgeTone } from '../../components/ui/Badge'
import type { DocumentView } from '../../api/generated'

/** 解析状态：联合类型直接来自 OpenAPI 生成物，改后端口径这里会编译报错。 */
export type ParseStatus = DocumentView['status']

/** 唯一的非终态：其余三个（已完成 / 有冲突 / 失败）都到站。 */
const PROCESSING: ParseStatus = '处理中'

/** 这份资料的解析还没结束吗？（决定要不要继续轮询） */
export function isProcessing(status: ParseStatus): boolean {
  return status === PROCESSING
}

/** 列表里还有资料在解析吗？——轮询开关的判定口径。 */
export function hasProcessing(documents: readonly DocumentView[] | undefined): boolean {
  return (documents ?? []).some((document) => isProcessing(document.status))
}

/** 需要教师看一眼的状态：有冲突要裁决、失败要重新上传。 */
const NEEDS_ATTENTION: readonly ParseStatus[] = ['有冲突', '失败']

export function statusTone(status: ParseStatus): BadgeTone {
  return NEEDS_ATTENTION.includes(status) ? 'accent' : 'outline'
}

/** 状态的短解释：标签悬停与读屏用的一句话。 */
export const STATUS_HINT: Record<ParseStatus, string> = {
  处理中: '后台还在解析，界面会自动跟进到终态，不需要手动刷新。',
  已完成: '已入库可检索。',
  有冲突: '已入库，但检测出待裁决的矛盾；裁决前新的知识点不进知识图谱。',
  失败: '解析没有成功，可按原文重新上传。',
}

/** 状态的长说明：详情页用同一份口径的完整句式。 */
export const STATUS_NOTE: Record<ParseStatus, string> = {
  处理中: '处理中：正在解析、分块与入库；完成后这里的状态会自动更新，不需要手动刷新。',
  已完成: '已入库可检索。标记为参考资料后，备课检索会加权，生成物里也会溯源到这份资料。',
  有冲突: '已入库，但检测出待裁决的矛盾；裁决前新的知识点不进知识图谱。',
  失败: '解析没有成功。请按原文重新上传这份资料。',
}
