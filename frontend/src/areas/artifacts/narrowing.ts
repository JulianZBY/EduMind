/**
 * 生成物版本的读法与修改意见的组装（纯函数）。
 *
 * 两件事都不该住进组件：
 *
 * 1. **内容快照的读法**：版本详情里的 `content` 在 OpenAPI 里是自由字典
 *    （课件 slides / 教案结构 / 提纲正文 / 题目 / 互动内容 HTML）。界面不把它当已知形状取字段，
 *    也不手抄一份接口类型（ADR-0005），而是白名单式收窄——字段缺失或类型不对就跳过，
 *    读不出来就展示「这一版没有可回看的内容」，新增键天然向前兼容。
 * 2. **修改意见的组装**：`buildRevisionRequest` 决定「哪一类生成物走哪个端点、请求体带什么」。
 *    它只带**所选这一版的内容 + 修改意见 + 基线版本**，因此天然满足「修改意见只作用所选生成物」。
 */
import type {
  ArtifactVersionItem,
  ReviseApiV1RevisePostData,
  ReviseExamEndpointApiV1ReviseExamPostData,
  ReviseExamRequest,
  ReviseInteractiveEndpointApiV1ReviseInteractivePostData,
  ReviseInteractiveRequest,
  ReviseOutlineEndpointApiV1ReviseOutlinePostData,
  ReviseOutlineRequest,
  ReviseRequest,
  ReviseWordEndpointApiV1ReviseWordPostData,
  ReviseWordRequest,
} from '../../api/generated'
import { ApiError } from '../../api/client'

/**
 * 五类生成物（CONTEXT.md「生成物」）的类别与展示次序。
 * 取值与生成的 schema 同源（`ArtifactVersionItem['artifact_type']`），顺序是词汇表的次序。
 */
export type ArtifactType = ArtifactVersionItem['artifact_type']
export const ARTIFACT_TYPES: readonly ArtifactType[] = ['课件', '教案', '提纲', '试卷', '互动内容']

/** 备课会话区并排预览的三类「文档型」生成物（另有试卷 / 互动内容在下方入口里）。 */
export const PREVIEW_TYPES: readonly ArtifactType[] = ['课件', '教案', '提纲']

/** 「第 N 版」：教师看到的版本号（文件名不可读，不当标题用）。 */
export function versionLabel(version: number): string {
  return `第 ${version} 版`
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asTextList(value: unknown): readonly string[] {
  if (!Array.isArray(value)) return []
  return value.map(asText).filter((item) => item.trim().length > 0)
}

// ---- 内容快照的读法 ----

/** 课件的一页：role 是页面角色（封面 / 目录 / 内容 / 总结），points 是要点。 */
export interface SlideView {
  readonly role: string
  readonly title: string
  readonly points: readonly string[]
}

/** 教案的一步教学过程。 */
export interface ProcessStepView {
  readonly stage: string
  readonly minutes: number | null
  readonly content: string
}

/** 教案结构（读得出来的那部分；缺失的段落在界面上就不展示）。 */
export interface WordView {
  readonly knowledge: readonly string[]
  readonly ability: readonly string[]
  readonly emotion: readonly string[]
  readonly keyPoints: readonly string[]
  readonly difficultPoints: readonly string[]
  readonly process: readonly ProcessStepView[]
  readonly activities: readonly string[]
  readonly homework: readonly string[]
}

/** 试卷里的一道题（含考查知识点标注）。 */
export interface ExamQuestionView {
  readonly type: string
  readonly content: string
  readonly options: readonly string[]
  readonly answer: string
  readonly analysis: string
  readonly knowledgePoint: string
}

/** 课件内容快照 → 可展示的页面列表。 */
export function readSlides(content: unknown): readonly SlideView[] {
  const slides = asRecord(content)?.slides
  if (!Array.isArray(slides)) return []
  return slides.flatMap((slide) => {
    const record = asRecord(slide)
    if (!record) return []
    const title = asText(record.title)
    const role = asText(record.role)
    const points = asTextList(record.points ?? record.bullets)
    if (!title && points.length === 0) return []
    return [{ role, title, points }]
  })
}

/** 教案内容快照 → 可展示的结构。 */
export function readWordDoc(content: unknown): WordView {
  const record = asRecord(content)?.word
  const word = asRecord(record) ?? {}
  const objectives = asRecord(word.objectives) ?? {}
  const process = Array.isArray(word.process) ? word.process : []
  return {
    knowledge: asTextList(objectives.knowledge),
    ability: asTextList(objectives.ability),
    emotion: asTextList(objectives.emotion),
    keyPoints: asTextList(word.key_points),
    difficultPoints: asTextList(word.difficult_points),
    process: process.flatMap((step) => {
      const item = asRecord(step)
      if (!item) return []
      const minutes = typeof item.minutes === 'number' ? item.minutes : null
      return [
        {
          stage: asText(item.stage),
          minutes,
          content: asText(item.content),
        },
      ]
    }),
    activities: asTextList(word.activities),
    homework: asTextList(word.homework),
  }
}

/** 提纲内容快照 → 正文（Markdown 文本）。 */
export function readOutlineText(content: unknown): string {
  const record = asRecord(content)
  if (!record) return ''
  const text = asText(record.text)
  if (text) return text
  // 早期形态：提纲只有正文、没有落盘文件，快照里也可能直接是字符串
  return typeof content === 'string' ? content : ''
}

/** 试卷内容快照 → 题目列表。 */
export function readExamQuestions(content: unknown): readonly ExamQuestionView[] {
  const questions = asRecord(content)?.questions
  if (!Array.isArray(questions)) return []
  return questions.flatMap((question) => {
    const record = asRecord(question)
    if (!record) return []
    return [
      {
        type: asText(record.type),
        content: asText(record.content),
        options: asTextList(record.options),
        answer: asText(record.answer),
        analysis: asText(record.analysis),
        knowledgePoint: asText(record.knowledge_point),
      },
    ]
  })
}

/** 互动内容内容快照 → 单文件 HTML。 */
export function readHtml(content: unknown): string {
  return asText(asRecord(content)?.html)
}

/** 一份版本的内容概览：按类别给出「一眼看得懂」的摘要，读不出来就是空的。 */
export type ArtifactPreview =
  | { readonly form: 'slides'; readonly slides: readonly SlideView[] }
  | { readonly form: 'word'; readonly word: WordView }
  | { readonly form: 'text'; readonly text: string }
  | { readonly form: 'questions'; readonly questions: readonly ExamQuestionView[] }
  | { readonly form: 'html'; readonly html: string }
  | { readonly form: 'none' }

/** 按生成物类别读这一版的内容快照（读不出来返回 `none`，界面不假装有内容）。 */
export function readArtifactPreview(artifactType: ArtifactType, content: unknown): ArtifactPreview {
  switch (artifactType) {
    case '课件': {
      const slides = readSlides(content)
      return slides.length > 0 ? { form: 'slides', slides } : { form: 'none' }
    }
    case '教案':
      return { form: 'word', word: readWordDoc(content) }
    case '提纲': {
      const text = readOutlineText(content)
      return text ? { form: 'text', text } : { form: 'none' }
    }
    case '试卷': {
      const questions = readExamQuestions(content)
      return questions.length > 0 ? { form: 'questions', questions } : { form: 'none' }
    }
    case '互动内容': {
      const html = readHtml(content)
      return html ? { form: 'html', html } : { form: 'none' }
    }
    default:
      // 服务端将来新增类别时：界面只把它当「没有可回看的内容」，不崩也不瞎猜
      return { form: 'none' }
  }
}

// ---- 版本组（时间线）的读法 ----

/** 某一类的版本组；列表里没有这一类时返回 null（界面就不显示这条时间线）。 */
export function groupOfType(groups: readonly { artifact_type: ArtifactType }[], artifactType: ArtifactType) {
  return groups.find((group) => group.artifact_type === artifactType) ?? null
}

/** 组内某一版；找不到时退回当前版本（URL 里的版本被删掉时界面不空转）。 */
export function versionOf(
  group: { readonly versions: readonly ArtifactVersionItem[]; readonly current_version_id: string },
  versionId: string | null,
): ArtifactVersionItem | null {
  const versions = group.versions
  if (versions.length === 0) return null
  const picked = versions.find((version) => version.id === versionId)
  if (picked) return picked
  return versions.find((version) => version.id === group.current_version_id) ?? versions[versions.length - 1]
}

/** 「由哪一版衍生而来」：把 `parent_id` 翻成可读的「由第 N 版衍生」。 */
export function parentLabel(
  versions: readonly ArtifactVersionItem[],
  version: ArtifactVersionItem,
): string | null {
  if (!version.parent_id) return null
  const parent = versions.find((item) => item.id === version.parent_id)
  return parent ? `由${versionLabel(parent.version)}衍生` : '由更早的一版衍生'
}

// ---- 修改意见 → 请求（哪一类走哪个端点、请求体带什么）----
/** 修改端点的地址：取自生成的 schema（不手抄路径）。 */
const reviseUrl: ReviseApiV1RevisePostData['url'] = '/api/v1/revise'
const reviseWordUrl: ReviseWordEndpointApiV1ReviseWordPostData['url'] = '/api/v1/revise/word'
const reviseOutlineUrl: ReviseOutlineEndpointApiV1ReviseOutlinePostData['url'] =
  '/api/v1/revise/outline'
const reviseExamUrl: ReviseExamEndpointApiV1ReviseExamPostData['url'] = '/api/v1/revise/exam'
const reviseInteractiveUrl: ReviseInteractiveEndpointApiV1ReviseInteractivePostData['url'] =
  '/api/v1/revise/interactive'

/**
 * 一次修改的输入：**所选的那一版**（`baseVersionId`）+ 它的内容快照 + 修改意见。
 * 会话与基线都带上，服务端据此产出「版本号更高的新版本」，原版本保持可取回。
 */
export interface RevisionInput {
  readonly artifactType: ArtifactType
  readonly sessionId: string
  readonly baseVersionId: string
  readonly feedback: string
  readonly content: unknown
  /** 课件修改沿用原风格偏好（配色主题）；不传则回退默认主题。 */
  readonly style?: string
}

/** 修改请求体：五类生成物各一个（形状取自生成的 schema）。 */
export type RevisionBody =
  | ReviseRequest
  | ReviseWordRequest
  | ReviseOutlineRequest
  | ReviseExamRequest
  | ReviseInteractiveRequest

export type RevisionPlan =
  | { readonly ok: true; readonly url: string; readonly body: RevisionBody }
  | { readonly ok: false; readonly reason: string }

const NO_CONTENT = '这一版没有可修改的内容快照，换一版试试。'

function nonEmptyList(value: unknown): unknown[] | null {
  return Array.isArray(value) && value.length > 0 ? value : null
}

function nonEmptyRecord(value: unknown): Record<string, unknown> | null {
  const record = asRecord(value)
  return record && Object.keys(record).length > 0 ? record : null
}

/**
 * 组装「按修改意见重做所选生成物」的请求：地址 + 请求体。
 *
 * 请求体只含**这一版**的内容、修改意见与基线版本——不掺别的生成物、不带全量历史，
 * 这就是「修改意见只作用于所选生成物」在数据层的保证。内容快照读不出来时明确拒绝
 * （`ok: false` + 原因），不发出一个没有内容的修改请求。
 */
export function buildRevisionRequest(input: RevisionInput): RevisionPlan {
  const { sessionId, baseVersionId, feedback, content } = input
  switch (input.artifactType) {
    case '课件': {
      const slides = nonEmptyList(asRecord(content)?.slides)
      if (!slides) return { ok: false, reason: NO_CONTENT }
      const body: ReviseRequest = {
        slides: slides as ReviseRequest['slides'],
        feedback,
        style: input.style ?? '',
        session_id: sessionId,
        base_version_id: baseVersionId,
      }
      return { ok: true, url: reviseUrl, body }
    }
    case '教案': {
      const word = nonEmptyRecord(asRecord(content)?.word)
      if (!word) return { ok: false, reason: NO_CONTENT }
      const body: ReviseWordRequest = {
        word,
        feedback,
        session_id: sessionId,
        base_version_id: baseVersionId,
      }
      return { ok: true, url: reviseWordUrl, body }
    }
    case '提纲': {
      const text = readOutlineText(content)
      if (!text) return { ok: false, reason: NO_CONTENT }
      const body: ReviseOutlineRequest = {
        text,
        feedback,
        session_id: sessionId,
        base_version_id: baseVersionId,
      }
      return { ok: true, url: reviseOutlineUrl, body }
    }
    case '试卷': {
      const questions = nonEmptyList(asRecord(content)?.questions)
      if (!questions) return { ok: false, reason: NO_CONTENT }
      const body: ReviseExamRequest = {
        questions: questions as ReviseExamRequest['questions'],
        feedback,
        session_id: sessionId,
        base_version_id: baseVersionId,
      }
      return { ok: true, url: reviseExamUrl, body }
    }
    case '互动内容': {
      const html = readHtml(content)
      if (!html) return { ok: false, reason: NO_CONTENT }
      const body: ReviseInteractiveRequest = {
        html,
        feedback,
        session_id: sessionId,
        base_version_id: baseVersionId,
      }
      return { ok: true, url: reviseInteractiveUrl, body }
    }
    default:
      // 服务端将来新增类别时，界面不假装能改它（读不出端点就明确拒绝）
      return { ok: false, reason: '这一类生成物暂时不支持按修改意见重做。' }
  }
}

/** 失败说法：404 = 基线/会话没了；422 = 基线类型不符（前端不该出现，出现就说明选错了版本）。 */
export function revisionFailureMessage(error: unknown): string {
  const status = (error as { status?: number } | null)?.status
  if (status === 404) return '这一版不在服务端了：刷新生成物时间线，重选一版再改。'
  if (status === 422) return '后端不接受这次修改（基线版本与生成物类别不符）：重选一版再改。'
  if (error instanceof Error && error.message && !('status' in error)) return error.message
  return '没改上：后端暂时做不了这次修改，重试即可。'
}

// ---- 按需生成（试卷 / 互动内容）的纯函数 ----

/** 生成响应里的版本号可空：缺席时退回不带版本号的说法。 */
export function producedVersionLabel(version: number | null | undefined): string {
  return typeof version === 'number' ? versionLabel(version) : '新版本'
}

/** 生成失败的说法：502 = 模型没给出可用结果（没落半成品），与「后端连不上」分开讲。 */
export function generationFailureMessage(error: unknown, kind: string): string {
  if (error instanceof ApiError) {
    if (error.status === 502) return `模型这次没给出可用的${kind}，也没落半成品：重试即可。`
    if (error.status === 404) return '这次备课在服务端找不到了：回备课会话列表重选一次。'
  }
  return `没生成成：后端暂时做不了这一次${kind}生成，重试即可。`
}

/**
 * 备课意图对象（服务端 `intent` 是自由结构，缺字段时退化为仅凭主题生成）。
 * 只带教师在这一个弹层里填的东西，不清空也不猜别的字段。
 */
export function buildIntent(input: {
  topic: string
  grade: string
  minutes: string
  interactivity?: string
}): Record<string, unknown> {
  const intent: Record<string, unknown> = { topic: input.topic.trim() }
  if (input.grade.trim()) intent.grade = input.grade.trim()
  const minutes = Number.parseInt(input.minutes, 10)
  if (Number.isFinite(minutes) && minutes > 0) intent.duration_minutes = minutes
  if (input.interactivity?.trim()) intent.interactivity = input.interactivity.trim()
  return intent
}
