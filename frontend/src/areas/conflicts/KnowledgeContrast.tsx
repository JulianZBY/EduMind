/**
 * 新旧知识对照（CONTEXT.md 第 6 节）：左边是还没进图谱的新知，右边是库里的旧知识点。
 *
 * 两侧是**对照卡片**，不是「输入」与「上一版」。结构冲突的新知还会带上它自带的关系
 * （`new_knowledge.relations`，端点按知识点标题表达），这里如实列出，省得教师在图示里找。
 */
import type { ExistingKnowledgeEntry, NewKnowledgeEntry } from '../../api/generated'
import { Card, CardBody, CardHeader } from '../../components/ui'
import { readProposedRelations } from './proposedRelations'

export interface KnowledgeContrastProps {
  newKnowledge: NewKnowledgeEntry | null | undefined
  existingKnowledge: ExistingKnowledgeEntry | null | undefined
}

export function KnowledgeContrast({ newKnowledge, existingKnowledge }: KnowledgeContrastProps) {
  const relations = readProposedRelations(newKnowledge)

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader title="新知" meta="还没进图谱" />
        <CardBody className="flex flex-col gap-2">
          <p className="text-sm font-bold break-words">{newKnowledge?.title || '（没有标题）'}</p>
          <p className="text-sm leading-6 whitespace-pre-wrap text-black/80">
            {newKnowledge?.content || '（没有正文）'}
          </p>
          {relations.length > 0 ? (
            <ul className="flex flex-col gap-1 border-t-2 border-black pt-2 text-xs text-black/60">
              {relations.map((relation) => (
                <li key={`${relation.fromTitle}-${relation.toTitle}-${relation.relation}`}>
                  新知带来关系：{relation.fromTitle} —{relation.relation}→ {relation.toTitle}
                </li>
              ))}
            </ul>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="库里的旧知识点"
          meta={existingKnowledge?.id ? `节点 ${existingKnowledge.id.slice(0, 8)}…` : undefined}
        />
        <CardBody className="flex flex-col gap-2">
          {existingKnowledge ? (
            <>
              <p className="text-sm font-bold break-words">
                {existingKnowledge.title || '（没有标题）'}
              </p>
              <p className="text-sm leading-6 whitespace-pre-wrap text-black/80">
                {existingKnowledge.content || '（没有正文）'}
              </p>
            </>
          ) : (
            <p className="text-sm text-black/60">
              这条冲突没有对应的旧知识点：它问的是「要不要让这段内容进库」，不是「谁对」。
            </p>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
