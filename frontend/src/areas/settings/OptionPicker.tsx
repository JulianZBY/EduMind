import { Button } from '../../components/ui/Button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '../../components/ui/DropdownMenu'
import { ChevronDownIcon } from '../../components/ui/icons'

/**
 * 选项选择器（设置页专用）：下拉项来自后端目录（供应商 / 能力实现 / 模型档位），前端不另立清单。
 *
 * 用库里的 DropdownMenu（Radix）而不是原生 select：弹层样式、键盘导航、Esc 关闭都由原语承担，
 * 黑白反色与聚焦轮廓与其它可交互元素一致（风格文档第 3 节）。
 */
export interface PickerOption {
  /** 配置取值（写进设置的就是它）。 */
  id: string
  /** 面向教师的说明。 */
  label: string
  /** 下拉里的补充说明（如就绪状态），可选。 */
  note?: string
}

export interface OptionPickerProps {
  id: string
  /** 当前值；空字符串是合法取值（如「未设置，回落全局默认」）。 */
  value: string
  options: PickerOption[]
  onChange: (id: string) => void
  /** 下拉标题（说明这一列在选什么）。 */
  menuLabel?: string
  disabled?: boolean
  /** 无障碍标签：此选择器在为什么字段取值。 */
  'aria-label'?: string
}

export function OptionPicker({
  id,
  value,
  options,
  onChange,
  menuLabel,
  disabled = false,
  'aria-label': ariaLabel,
}: OptionPickerProps) {
  const current = options.find((option) => option.id === value)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          id={id}
          aria-label={ariaLabel}
          disabled={disabled}
          className="w-full justify-between text-left font-normal"
        >
          <span className="truncate">{current ? current.label : value || '未设置'}</span>
          <ChevronDownIcon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="max-h-80 w-[var(--radix-dropdown-menu-trigger-width)] overflow-y-auto"
      >
        {menuLabel ? <DropdownMenuLabel>{menuLabel}</DropdownMenuLabel> : null}
        {options.map((option) => (
          <DropdownMenuItem
            key={option.id}
            onSelect={() => onChange(option.id)}
            className={option.id === value ? 'font-bold' : undefined}
          >
            <span className="flex flex-col items-start gap-0.5 text-left">
              <span>{option.label}</span>
              {option.note ? <span className="text-xs font-normal text-black/60">{option.note}</span> : null}
            </span>
            <span aria-hidden="true" className="shrink-0">
              {option.id === value ? '当前' : ''}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
