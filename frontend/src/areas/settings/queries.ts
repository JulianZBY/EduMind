/**
 * 设置区的服务端状态（TanStack Query）。
 * 约定：query key 以 `settingsKeys.all` 打头，hooks 只住本文件（票 13 在此追加配置读写与掩码回读）。
 */
export const settingsKeys = {
  all: ['settings'] as const,
}
