/**
 * 类名拼接：只做过滤与连接，不引入样式方案（栈固定为 Tailwind，见 ADR-0005）。
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
