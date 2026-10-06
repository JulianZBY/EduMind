/**
 * 上传体积口径：与后端 `settings.max_upload_bytes` 对齐的唯一事实源（B3）。
 *
 * 后端默认 200 MB（`backend/app/config.py` 的 `max_upload_bytes`），超出即返回 413，
 * 且是「整份读入后再拒」（`backend/app/api/v1/documents.py`）。这里硬编码同一口径，
 * 让超限在本地就被挡下——不再整份传完才吃后端拒绝。
 * 后端若调大/调小该值，这里必须同步改。
 */
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024

/** 上限的可读文案（弹层提示用），与上面常量同源，避免两处各写一份数字。 */
export const MAX_UPLOAD_LABEL = `${MAX_UPLOAD_BYTES / (1024 * 1024)} MB`

/** 单份文件是否在上限内（含等于上限）。 */
export function isWithinUploadLimit(size: number): boolean {
  return size <= MAX_UPLOAD_BYTES
}

/** 把字节数翻成教师能读的体量文案，用于「这份文件多大」的提示。 */
export function formatFileSize(bytes: number): string {
  const mb = bytes / (1024 * 1024)
  if (mb >= 1) return `${mb.toFixed(1)} MB`
  const kb = bytes / 1024
  if (kb >= 1) return `${Math.round(kb)} KB`
  return `${bytes} B`
}
