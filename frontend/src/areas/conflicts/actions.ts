/**
 * 冲突三分类的裁决动作目录（CONTEXT.md 第 6 节 / ADR-0004 的动作集合）。
 *
 * 前端为什么要有这份表：按钮文案、按下之后会变成什么终态、以及「哪几种动作属于这一类」
 * 都要一致地呈现，散在三个卡片里就会各自漂移。
 *
 * 纪律：
 * - 动作取值来自生成的 schema（`ReviewRequest['action']`），后端一改，`tsc` 就报——
 *   不在这里手抄接口类型；
 * - 后端的动作集合（`ACTIONS_BY_CATEGORY`）是唯一事实源，本表只是它的呈现；
 *   两者一致有可复现校验（见票 11 交付记录里的临时比对脚本）。
 */
import type { ReviewRequest } from '../../api/generated'

export type ReviewAction = ReviewRequest['action']

/** 冲突终态（CONTEXT.md 第 6 节 / `docs/api/conflicts.md` 的状态机）。 */
export type DecisionStatus = '已接受' | '已拒绝' | '并存'

export const CONFLICT_CATEGORIES = ['定义冲突', '结构冲突', '常识存疑'] as const
export type ConflictCategory = (typeof CONFLICT_CATEGORIES)[number]

/** 类别 ↔ 搜索参数（区内的类别分区用 `?category=` 寻址，刷新与分享不丢上下文）。 */
export const CATEGORY_SLUGS: Record<ConflictCategory, string> = {
  定义冲突: 'definition',
  结构冲突: 'structure',
  常识存疑: 'common-sense',
}

/** 后端给的是中文字符串，读不到或认不出时按定义冲突处理（与后端默认口径一致）。 */
export function asCategory(value: string | null | undefined): ConflictCategory {
  return CONFLICT_CATEGORIES.find((category) => category === value) ?? '定义冲突'
}

export function categoryFromSlug(slug: string | null): ConflictCategory {
  return CONFLICT_CATEGORIES.find((category) => CATEGORY_SLUGS[category] === slug) ?? '定义冲突'
}

export interface ConflictActionOption {
  readonly action: ReviewAction
  /** 按下这个按钮后冲突的终态（与后端 `STATUS_BY_ACTION` 一致）。 */
  readonly status: DecisionStatus
  /** 按钮旁的一句说明：按下去对图谱 / 入库做了什么。 */
  readonly hint: string
  /** 需要谨慎的动作（拒绝、编辑修正）用强调色底。 */
  readonly accent?: boolean
}

export const ACTIONS_BY_CATEGORY: Record<ConflictCategory, readonly ConflictActionOption[]> = {
  定义冲突: [
    { action: '接受新', status: '已接受', hint: '新知替换旧知识点，旧知识点上的关系改挂到新知' },
    { action: '保留旧', status: '已拒绝', hint: '丢弃新知，图谱不动' },
    { action: '并存', status: '并存', hint: '新旧都保留，差异说明留在冲突记录里' },
  ],
  结构冲突: [
    { action: '接受新', status: '已接受', hint: '新知顶替旧知识点，旧知识点的关系改挂到新知' },
    { action: '保留旧', status: '已拒绝', hint: '丢弃新知，图谱保持现状' },
    { action: '并存', status: '并存', hint: '新旧都保留在图谱里，差异说明留在冲突记录里' },
  ],
  常识存疑: [
    { action: '照常入库', status: '已接受', hint: '内容没问题，按原文进库' },
    { action: '拒绝', status: '已拒绝', hint: '不让它进库', accent: true },
    {
      action: '编辑修正后入库',
      status: '已接受',
      hint: '入库的是你改对后的内容，原文留在冲突记录里',
      accent: true,
    },
  ],
}

/**
 * 终态 → 面向教师的说法。
 *
 * 「并存」与「已接受」的呈现不同（CONTEXT.md：并存 = 新旧都留），
 * 故裁决成功后不要乐观地把整条冲突从队列里删掉。
 */
export const STATUS_LABELS: Record<string, string> = {
  待审: '待审',
  已接受: '已接受',
  已拒绝: '已拒绝',
  并存: '并存',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}
