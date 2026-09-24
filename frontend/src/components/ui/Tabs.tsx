import * as TabsPrimitive from '@radix-ui/react-tabs'
import type { ComponentProps } from 'react'
import { cn } from '../../lib/cn'

/**
 * 标签页（Radix Tabs 承担键盘方向键切换与 roving focus）。
 * 当前项用「黑白反色 + 强调色左边线」双重表达，不靠阴影或圆角。
 */
export function Tabs(props: ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root {...props} />
}

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn('flex flex-wrap items-stretch gap-2 border-b-2 border-black px-3 py-2', className)}
      {...props}
    />
  )
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        'inline-flex h-7 items-center gap-2 rounded-none border-2 border-black bg-white px-2 text-xs text-black',
        'outline-none transition-colors duration-150 hover:bg-black hover:text-white',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black',
        'disabled:pointer-events-none disabled:border disabled:border-black/40 disabled:text-black/40',
        'data-[state=active]:border-l-4 data-[state=active]:border-l-[#ff3366] data-[state=active]:bg-black data-[state=active]:text-white',
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      className={cn('flex-1 outline-none focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-black', className)}
      {...props}
    />
  )
}
