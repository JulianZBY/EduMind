/**
 * 工作台里的时间口径（纯函数，三处列表/对话共用一份，避免各写一份格式化）。
 * 后端回的是 naive 本地时间（如 `2026-09-24T10:20:00`，见 `app/db/models.py`），
 * 所以直接按本地时间解析、不做时区换算。
 */
export function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (part: number) => String(part).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}
