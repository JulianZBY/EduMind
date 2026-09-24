/**
 * 自由结构的读法（纯函数）。
 *
 * 两处后端字段在 OpenAPI 里不是强类型：生成记录 `artifacts` 是自由 dict，知识库资料列表
 * 目前没有 `response_model`（`src/api/generated` 里的响应类型就是 `unknown`）。
 * 界面不能把它们当已知形状取字段，但**也不允许手抄一份接口类型**（ADR-0005）。
 *
 * 于是这里做白名单式收窄：字段缺失或类型不对就跳过，只保留界面真正要用的部分。
 * 生成记录的历史版本、后续新增的键都天然向前兼容（读不出来就不展示，不会崩）。
 */

/** 回复形态（CONTEXT.md）：助手消息只属于一种形态；没有形态的（教师说的）读成 null。 */
export type ReplyForm = '澄清回复' | '生成回复'

const REPLY_FORMS: readonly ReplyForm[] = ['澄清回复', '生成回复']

/** 读回复形态：只认词汇表里的两个术语，其余（空、旧数据、未知取值）都当作没有形态。 */
export function readReplyForm(kind: unknown): ReplyForm | null {
  return REPLY_FORMS.find((form) => form === kind) ?? null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

// ---- 知识库资料（参考资料勾选用）----

/** 一份教学资料里，勾选参考资料真正要用的字段。 */
export interface KnowledgeDocument {
  readonly id: string
  readonly filename: string
  /** 解析状态（CONTEXT.md）：处理中 / 已完成 / 有冲突 / 失败 */
  readonly status: string
  /** 参考资料标记：知识库里的「备课时优先使用」标记 */
  readonly isReference: boolean
}

/** 能不能把这份资料勾成本次备课的参考资料：只有已入库的资料可检索（处理中/失败的不行）。 */
export function isUsableReference(document: KnowledgeDocument): boolean {
  return document.status === '已完成' || document.status === '有冲突'
}

/** 读一份资料（上传响应与列表里的一行同形）。缺 id 或文件名就无法在界面上核对，直接跳过。 */
export function readKnowledgeDocument(value: unknown): KnowledgeDocument | null {
  const record = asRecord(value)
  if (!record) return null
  const id = asText(record.id)
  const filename = asText(record.filename)
  if (!id || !filename) return null
  return {
    id,
    filename,
    status: asText(record.status) ?? '处理中',
    isReference: record.is_reference === true,
  }
}

/** 读资料列表响应：形状不对就当空列表（空列表是「知识库里还没有资料」的正常状态）。 */
export function readKnowledgeDocuments(payload: unknown): KnowledgeDocument[] {
  const items = asRecord(payload)?.documents
  if (!Array.isArray(items)) return []
  return items
    .map(readKnowledgeDocument)
    .filter((document): document is KnowledgeDocument => document !== null)
}

// ---- 生成记录（生成回复里的最小结果入口）----

/**
 * 一条生成物入口：能落盘下载的是「文件」，只有正文的是「文本」（提纲目前就是 Markdown 文本）。
 */
export type GenerationEntry =
  | {
      readonly form: 'file'
      readonly label: string
      readonly filename: string
      /** 互动内容可在新标签页直接打开试用（`inline=true`），其余走下载 */
      readonly openInTab: boolean
    }
  | { readonly form: 'text'; readonly label: string; readonly text: string }

/** 文件名：优先 `filename`，退回 `path` 的最后一段（两者后端都出现过）。 */
function fileNameOf(record: Record<string, unknown>): string | null {
  const direct = asText(record.filename)
  if (direct) return direct
  const path = asText(record.path)
  if (!path) return null
  const name = path.split(/[\\/]/).pop() ?? ''
  return name.trim() || null
}

function fileEntry(value: unknown, label: string, openInTab: boolean): GenerationEntry | null {
  const record = asRecord(value)
  if (!record) return null
  const filename = fileNameOf(record)
  if (!filename) return null
  return { form: 'file', label, filename, openInTab }
}

function outlineEntry(value: unknown): GenerationEntry | null {
  const text = asText(value)
  if (text) return { form: 'text', label: '提纲', text }
  const record = asRecord(value)
  if (!record) return null
  // 提纲的两种形态都在：正文（早期版本只有文本）与「正文 + 落盘文件」（票 07 起与课件/教案同形）。
  // 有可下载文件就给下载入口，只有正文时退回可展开的文本。
  return fileEntry(record, '提纲', false) ?? textEntry(record.text, '提纲')
}

/** 只有正文、没有落盘文件的生成物（如仍未落盘的提纲）。 */
function textEntry(value: unknown, label: string): GenerationEntry | null {
  const text = asText(value)
  return text ? { form: 'text', label, text } : null
}

/**
 * 读一条生成回复里的生成物入口，顺序固定为课件 → 教案 → 提纲 → 互动内容。
 * 生成环节允许个别生成物失败（后端降级为空），因此读不出来就不列，不报错。
 */
export function readGenerationEntries(artifacts: unknown): GenerationEntry[] {
  const record = asRecord(artifacts)
  if (!record) return []
  const entries: GenerationEntry[] = []
  const ppt = fileEntry(record.ppt, '课件', false)
  if (ppt) entries.push(ppt)
  const word = fileEntry(record.word, '教案', false)
  if (word) entries.push(word)
  const outline = outlineEntry(record.outline)
  if (outline) entries.push(outline)
  const interactive = fileEntry(record.interactive, '互动内容', true)
  if (interactive) entries.push(interactive)
  return entries
}

/** 本次命中的参考资料名（生成回复附的溯源）。 */
export function readReferenceNames(artifacts: unknown): string[] {
  const names = asRecord(artifacts)?.references
  if (!Array.isArray(names)) return []
  return names.map(asText).filter((name): name is string => name !== null)
}

/** 是否命中了本地知识库；读不出来返回 null（界面就不提这一句）。 */
export function readKnowledgeHit(artifacts: unknown): boolean | null {
  const hit = asRecord(artifacts)?.knowledge_hits
  return typeof hit === 'boolean' ? hit : null
}
