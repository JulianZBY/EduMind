/**
 * 生成物版本的内容预览（按类别呈现这一版的快照）。
 *
 * 纯渲染组件：内容由 `narrowing.ts` 的读法收窄成已知形状后传进来，这里不解析原始 dict，
 * 也不做数据请求——备课会话区的并排预览与生成物区的回看列共用本组件，两处显示同一份内容。
 */
import { Badge } from '../../components/ui/Badge'
import type { ArtifactType, SlideView } from './narrowing'
import { readArtifactPreview, versionLabel } from './narrowing'
import type { ArtifactVersion } from './queries'

/** 一列小标题（工作台密度：小字号 + 贴边分隔线）。 */
function SectionTitle({ children }: { children: string }) {
  return <p className="mt-2 border-b-2 border-black pb-0.5 text-xs font-bold">{children}</p>
}

function SlideList({ slides }: { slides: readonly SlideView[] }) {
  return (
    <ol className="mt-1 flex flex-col gap-1">
      {slides.map((slide, index) => (
        <li key={`${index}-${slide.title}`} className="rounded-none border-2 border-black px-2 py-1">
          <p className="text-xs font-bold">
            {index + 1}. {slide.title || '（未命名页）'}
            {slide.role ? <span className="ml-1 font-normal text-black/60">{slide.role}</span> : null}
          </p>
          {slide.points.length > 0 ? (
            <ul className="mt-0.5 flex list-disc flex-col pl-4 text-xs leading-5">
              {slide.points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ol>
  )
}

/** 一行「标签：内容」的教案段落（空段落不显示）。 */
function WordLine({ label, items }: { label: string; items: readonly string[] }) {
  if (items.length === 0) return null
  return (
    <p className="mt-1 text-xs leading-5">
      <span className="font-bold">{label}：</span>
      {items.join('；')}
    </p>
  )
}

export interface ArtifactPreviewProps {
  artifactType: ArtifactType
  /** 这一版的内容快照（来自版本详情，未经解析）。 */
  content: unknown
  /** 这一版的版本号（用于文案与「第 N 版」标注）。 */
  version?: number
  /** 互动内容的「在新标签页打开试用」地址（`inline=true`）；不传则不显示入口。 */
  openInTabUrl?: string
}

export function ArtifactPreview({ artifactType, content, version, openInTabUrl }: ArtifactPreviewProps) {
  const preview = readArtifactPreview(artifactType, content)

  if (preview.form === 'none') {
    return (
      <p className="px-3 py-2 text-xs leading-5 text-black/60">
        {version ? `${versionLabel(version)}的` : '这一版的'}
        {artifactType}没有可回看的内容快照。可以下载文件，或到生成物区看它的落盘文件与版本时间线。
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-1 px-3 py-2">
      {preview.form === 'slides' ? <SlideList slides={preview.slides} /> : null}

      {preview.form === 'word' ? (
        <>
          <WordLine label="知识目标" items={preview.word.knowledge} />
          <WordLine label="能力目标" items={preview.word.ability} />
          <WordLine label="情感目标" items={preview.word.emotion} />
          <WordLine label="教学重点" items={preview.word.keyPoints} />
          <WordLine label="教学难点" items={preview.word.difficultPoints} />
          {preview.word.process.length > 0 ? (
            <>
              <SectionTitle>教学过程</SectionTitle>
              <ol className="mt-1 flex flex-col gap-1">
                {preview.word.process.map((step, index) => (
                  <li key={`${index}-${step.stage}`} className="text-xs leading-5">
                    <span className="font-bold">
                      {index + 1}. {step.stage || '环节'}
                    </span>
                    {step.minutes === null ? null : `（${step.minutes} 分钟）`}
                    {step.content ? ` ${step.content}` : ''}
                  </li>
                ))}
              </ol>
            </>
          ) : null}
          <WordLine label="课堂活动" items={preview.word.activities} />
          <WordLine label="课后作业" items={preview.word.homework} />
        </>
      ) : null}

      {preview.form === 'text' ? (
        <pre className="text-xs leading-5 whitespace-pre-wrap">{preview.text}</pre>
      ) : null}

      {preview.form === 'questions' ? (
        <ol className="flex flex-col gap-1">
          {preview.questions.map((question, index) => (
            <li key={`${index}-${question.content}`} className="rounded-none border-2 border-black px-2 py-1">
              <p className="text-xs font-bold">
                {index + 1}. {question.type ? `[${question.type}]` : ''} {question.content}
              </p>
              {question.options.length > 0 ? (
                <ul className="mt-0.5 flex flex-col text-xs leading-5">
                  {question.options.map((option) => (
                    <li key={option}>{option}</li>
                  ))}
                </ul>
              ) : null}
              {question.answer ? (
                <p className="mt-0.5 text-xs leading-5 text-black/60">答案：{question.answer}</p>
              ) : null}
              {question.knowledgePoint ? (
                <p className="mt-0.5">
                  <Badge tone="outline">考查知识点：{question.knowledgePoint}</Badge>
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      {preview.form === 'html' ? (
        <div className="flex flex-col gap-2">
          <p className="text-xs leading-5 text-black/60">
            单文件 HTML5 互动内容（{preview.html.length} 字符）：在浏览器新标签页直接打开试用。
          </p>
          {openInTabUrl ? (
            <a
              href={openInTabUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex w-fit items-center gap-1 rounded-none border-2 border-black px-2 py-0.5 text-xs font-bold text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
            >
              在新标签页打开互动内容
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

/** 版本详情加载失败时的说明（生成物区与并排预览共用一套说法）。 */
export function VersionUnavailable({ version, onRetry }: { version: ArtifactVersion; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-2 px-3 py-2">
      <p className="text-xs leading-5">
        这一版（{versionLabel(version.version)}）取不到：后端暂时取不回它的内容快照。已入库的版本不会丢。
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex h-7 items-center gap-2 rounded-none border-2 border-black bg-white px-2 text-xs font-bold text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
      >
        重试
      </button>
    </div>
  )
}
