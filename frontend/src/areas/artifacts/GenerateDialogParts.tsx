/**
 * 按需生成弹层的共用件（试卷 / 互动内容两个入口共用）。
 *
 * 共用的是「意图怎么问、进行中怎么说、生成后给什么入口」这三件事——两个入口的区别只在
 * 生成什么，因此那部分各住自己的文件（`GenerateExamDialog` / `GenerateInteractiveDialog`）。
 * 纯函数（意图组装、失败说法）住 `narrowing.ts`，本文件只有界面。
 */
import { Field } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'

/** 进行中：文字 + 直角进度条（风格文档第 4 节：不用骨架屏灰块）。 */
export function PendingBar({ label }: { label: string }) {
  return (
    <div role="status" className="flex flex-col gap-2">
      <p className="text-sm leading-6">{label}</p>
      <div className="h-1.5 w-full rounded-none border-2 border-black">
        <div className="h-full w-1/3 bg-black" />
      </div>
    </div>
  )
}

const linkClass =
  'inline-flex h-7 items-center gap-1 rounded-none border-2 border-black bg-white px-2 text-xs font-bold text-black outline-none transition-colors duration-150 hover:bg-black hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black'

/** 生成成功后的下一步：一句话结果 + 一两个入口（链接都是教师点击，不会被浏览器拦弹窗）。 */
export function GeneratedLinks({
  summary,
  primaryHref,
  primaryLabel,
  primaryOpenInTab,
  secondaryHref,
  secondaryLabel,
}: {
  summary: string
  primaryHref: string
  primaryLabel: string
  primaryOpenInTab?: boolean
  secondaryHref?: string
  secondaryLabel?: string
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm leading-6">{summary}</p>
      <div className="flex flex-wrap items-center gap-2">
        <a
          href={primaryHref}
          className={linkClass}
          target={primaryOpenInTab ? '_blank' : undefined}
          rel={primaryOpenInTab ? 'noreferrer' : undefined}
        >
          {primaryLabel}
        </a>
        {secondaryHref && secondaryLabel ? (
          <a href={secondaryHref} className={linkClass}>
            {secondaryLabel}
          </a>
        ) : null}
      </div>
    </div>
  )
}

/** 备课意图的两个可选字段（主题在各自的弹层里必填，主题字段随弹层不同而措辞不同）。 */
export function GradeAndMinutesFields({
  idPrefix,
  grade,
  onGrade,
  minutes,
  onMinutes,
}: {
  idPrefix: string
  grade: string
  onGrade: (value: string) => void
  minutes: string
  onMinutes: (value: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-3">
      <Field htmlFor={`${idPrefix}-grade`} label="学段（可不填）">
        <Input
          id={`${idPrefix}-grade`}
          value={grade}
          placeholder="如：初二"
          onChange={(event) => onGrade(event.target.value)}
        />
      </Field>
      <Field htmlFor={`${idPrefix}-minutes`} label="时长（分钟，可不填）">
        <Input
          id={`${idPrefix}-minutes`}
          inputMode="numeric"
          value={minutes}
          placeholder="如：40"
          onChange={(event) => onMinutes(event.target.value)}
        />
      </Field>
    </div>
  )
}
