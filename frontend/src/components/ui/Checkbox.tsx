import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/cn'

export type CheckboxProps = ComponentProps<typeof CheckboxPrimitive.Root>

/** Radix 承担复选语义与 Space／Tab 交互；这里只提供直角、反色、聚焦与禁用皮肤。 */
export function Checkbox({ className, ...props }: CheckboxProps) {
  return (
    <CheckboxPrimitive.Root
      className={cn(
        'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-none border-2 border-black bg-white text-black',
        'outline-none transition-colors duration-150 hover:bg-black hover:text-white',
        'focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-black',
        'disabled:pointer-events-none disabled:border disabled:text-black/40',
        'data-[state=checked]:enabled:bg-black data-[state=checked]:enabled:text-white',
        'data-[state=checked]:enabled:hover:bg-white data-[state=checked]:enabled:hover:text-black',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator>
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="m3 8 3 3 7-7" stroke="currentColor" strokeWidth="2" />
        </svg>
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}
