/**
 * 一条待审冲突的卡片：三类别各呈现自己的形态与动作（CONTEXT.md 第 6 节）。
 *
 * - 定义冲突 = 新旧知识对照 + 三选一；
 * - 结构冲突 = 新旧对照 + 「图谱现状 vs 三种裁决终态」的小图 + 三选一；
 * - 常识存疑 = 红旗标记 + 原文 + 两选一 + 编辑修正后入库。
 *
 * 动作目录住 `actions.ts`（唯一一份），按钮下方写明按下之后的终态，
 * 让「终态与动作一一对应」在界面上是看得见的。
 */
import { useState } from 'react'
import type { ConflictItem } from '../../api/generated'
import { Badge, Button, Card, CardBody, CardFooter, CardHeader } from '../../components/ui'
import { CommonSenseOriginal } from './CommonSenseOriginal'
import { KnowledgeContrast } from './KnowledgeContrast'
import { StructureOutcomes } from './StructureOutcomes'
import { ACTIONS_BY_CATEGORY, asCategory, statusLabel } from './actions'
import type { ReviewAction } from './actions'

export interface ConflictCardProps {
  conflict: ConflictItem
  /** 这条冲突的动作正在提交中（按钮置灰，避免重复裁决）。 */
  pending: boolean
  onDecide: (action: ReviewAction, revisedContent?: string) => void
}

export function ConflictCard({ conflict, pending, onDecide }: ConflictCardProps) {
  const category = asCategory(conflict.category)
  const decided = conflict.status !== '待审'
  const [revisedContent, setRevisedContent] = useState('')
  const original = conflict.new_knowledge?.content ?? ''
  const options = ACTIONS_BY_CATEGORY[category]

  return (
    <Card>
      <CardHeader
        title={conflict.new_knowledge?.title || '（没有标题的新知识）'}
        meta={`${category} · 冲突 ${conflict.id.slice(0, 8)}…`}
        actions={
          <Badge tone={decided ? 'solid' : 'accent'}>{statusLabel(conflict.status)}</Badge>
        }
      />
      <CardBody className="flex flex-col gap-3">
        {category === '常识存疑' ? (
          <CommonSenseOriginal
            original={original}
            revisedContent={revisedContent}
            onRevisedChange={setRevisedContent}
            disabled={decided || pending}
          />
        ) : (
          <KnowledgeContrast
            newKnowledge={conflict.new_knowledge}
            existingKnowledge={conflict.existing_knowledge}
          />
        )}

        {category === '结构冲突' && conflict.structure_preview ? (
          <StructureOutcomes
            current={conflict.structure_preview.current}
            outcomes={conflict.structure_preview.outcomes}
          />
        ) : null}

        {conflict.diff_description ? (
          <p className="text-xs text-black/60">检测到的差异：{conflict.diff_description}</p>
        ) : null}
      </CardBody>
      <CardFooter className="flex-wrap items-stretch justify-start">
        {decided ? (
          <p className="text-xs text-black/60">
            这条冲突已经裁决过
            {conflict.review_action ? `（${conflict.review_action}）` : ''}，终态 {statusLabel(conflict.status)}；
            每条冲突只能裁决一次。
          </p>
        ) : (
          <div role="group" aria-label="裁决动作" className="flex flex-wrap gap-3">
            {options.map((option) => {
              const needsDraft = option.action === '编辑修正后入库'
              const draft = revisedContent.trim()
              return (
                <div key={option.action} className="flex w-52 flex-col gap-1">
                  <Button
                    size="sm"
                    variant={option.accent ? 'accent' : 'default'}
                    disabled={pending || (needsDraft && draft === '')}
                    onClick={() =>
                      onDecide(option.action, needsDraft ? draft : undefined)
                    }
                  >
                    {option.action}
                  </Button>
                  <p className="text-xs leading-5 text-black/60">
                    终态 {option.status}：{option.hint}
                  </p>
                </div>
              )
            })}
          </div>
        )}
      </CardFooter>
    </Card>
  )
}
