import { cn } from '../../lib/cn'

export interface FlatLoadingProps {
  /** 一句话说明在等什么（面向教师的口语，例如「正在画图谱…」）。 */
  text: string
  className?: string
}

/**
 * 加载态：文字 + 直角进度条（黑底，不用骨架屏灰块、不用循环动画）。
 * 图谱相关界面共用，保证空转时的形态也符合扁平标准。
 */
export function FlatLoading({ text, className }: FlatLoadingProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('flex flex-col items-start gap-2 px-3 py-4', className)}
    >
      <p className="text-sm text-black">{text}</p>
      <div aria-hidden="true" className="h-2 w-32 rounded-none border-2 border-black">
        <div className="h-full w-1/2 bg-black" />
      </div>
    </div>
  )
}
