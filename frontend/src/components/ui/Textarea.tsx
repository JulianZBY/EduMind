import type { TextareaHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

/**
 * 多行文本输入（备课会话的输入框用）。
 *
 * 四态与 Input 同一套口径（风格文档第 3 节）：
 * - 默认：白底黑字、`border-2 border-black`、`rounded-none`
 * - 悬停：边线加粗（2px→4px，`box-sizing: border-box` 故不位移）——输入类控件不做黑白反色，
 *   否则文字会被实心黑块盖住就不可读了
 * - 聚焦：`focus-visible:outline-2 outline-offset-2 outline-black`（非浏览器默认蓝圈）
 * - 禁用：边框 2px→1px + 文字降为 `text-black/40`
 * 错误态：`aria-invalid` 时边框转强调色（配 Field 的强调色文案）
 */
const base = [
  'block w-full resize-none rounded-none border-2 border-black bg-white px-2 py-1 text-sm text-black',
  'transition-colors duration-150 outline-none placeholder:text-black/40',
  'hover:border-4 focus-visible:border-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black',
  'disabled:cursor-not-allowed disabled:border disabled:border-black/40 disabled:bg-white disabled:text-black/40',
  'aria-invalid:border-[#ff3366]',
].join(' ')

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>

export function Textarea({ className, ...props }: TextareaProps) {
  return <textarea className={cn(base, className)} {...props} />
}
