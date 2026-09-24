/**
 * 追问粒度三档（CONTEXT.md「追问粒度」：快速 / 标准 / 精细）。
 *
 * 粒度只在澄清阶段起作用：档位越高追问的要素越多。改档位走服务端会话设置
 * （`PATCH /api/v1/sessions/{id}`），改完立即影响后续对话。
 */
import { cn } from '../../lib/cn'
import type { Granularity } from './queries'

/** 三档与各自的追问范围（口径与后端 `core/clarify.py` 的粒度字段表一致）。 */
const GRANULARITY_OPTIONS: readonly { value: Granularity; hint: string }[] = [
  { value: '快速', hint: '只确认时长与风格，问得最少' },
  { value: '标准', hint: '再确认教学目标与重点' },
  { value: '精细', hint: '连互动环节与教学方法一起问' },
]

const optionBase =
  'inline-flex h-7 shrink-0 items-center rounded-none border-2 border-black px-2 text-xs outline-none transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black disabled:pointer-events-none disabled:border disabled:border-black/40 disabled:bg-white disabled:text-black/40'

export interface GranularityPickerProps {
  /** 当前档位：直接用服务端会话上的取值（未知取值时三档都不高亮，不假装是标准档）。 */
  value: string
  onChange: (next: Granularity) => void
  disabled?: boolean
  /** 小字标签：编辑密度（对话框）里显示，工作台密度的标题条里也显示同一份文案。 */
  className?: string
}

export function GranularityPicker({
  value,
  onChange,
  disabled = false,
  className,
}: GranularityPickerProps) {
  const active = GRANULARITY_OPTIONS.find((option) => option.value === value)

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <span className="text-xs font-bold text-black/60">追问粒度</span>
      <div className="flex flex-wrap items-center gap-1">
        {GRANULARITY_OPTIONS.map((option) => {
          const selected = option.value === value
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              title={option.hint}
              disabled={disabled}
              onClick={() => onChange(option.value)}
              className={cn(
                optionBase,
                selected ? 'bg-black text-white' : 'bg-white text-black hover:bg-black hover:text-white',
              )}
            >
              {option.value}
            </button>
          )
        })}
      </div>
      {active ? <span className="text-xs text-black/60">{active.hint}</span> : null}
    </div>
  )
}
