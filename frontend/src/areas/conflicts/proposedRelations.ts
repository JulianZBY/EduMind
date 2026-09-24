/**
 * 结构化读取新知自带的关系（`new_knowledge.relations`）。
 *
 * 那一侧是检测阶段存下的 JSON，接口只保证已知字段有类型（其余键原样保留），
 * 所以这里做一次**形状校验**：认得出形状的条目才列出来，认不出的不当场猜。
 */
import type { NewKnowledgeEntry } from '../../api/generated'

export interface ProposedRelation {
  fromTitle: string
  toTitle: string
  relation: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function readText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function readProposedRelations(
  entry: NewKnowledgeEntry | null | undefined,
): ProposedRelation[] {
  const raw: unknown = entry?.['relations']
  if (!Array.isArray(raw)) return []
  return raw.flatMap((item) => {
    if (!isRecord(item)) return []
    const fromTitle = readText(item['from_title'])
    const toTitle = readText(item['to_title'])
    const relation = readText(item['relation'])
    return fromTitle && toTitle && relation ? [{ fromTitle, toTitle, relation }] : []
  })
}
