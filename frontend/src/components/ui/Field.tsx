import * as LabelPrimitive from '@radix-ui/react-label'
import type { ComponentProps, ReactNode } from 'react'
import { cn } from '../../lib/cn'

/** 标签：Radix 承担关联语义（点击聚焦到对应输入）。 */
export function Label({ className, ...props }: ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      className={cn(
        'block text-sm font-bold text-black transition-colors duration-150 hover:text-[#ff3366] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black data-[disabled]:text-black/40',
        className,
      )}
      {...props}
    />
  )
}

export interface FieldProps {
  /** 表单控件的 id：与 htmlFor 成对出现，标签才点得动。 */
  htmlFor: string
  label: string
  hint?: string
  /** 错误文案：强调色 + 明确文案，不用红绿蓝。 */
  error?: string
  children: ReactNode
}

export function Field({ htmlFor, label, hint, error, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={htmlFor} className={error ? 'text-[#ff3366]' : undefined}>
        {label}
      </Label>
      {children}
      {error ? (
        <p className="text-xs text-[#ff3366]">{error}</p>
      ) : hint ? (
        <p className="text-xs text-black/60">{hint}</p>
      ) : null}
    </div>
  )
}
