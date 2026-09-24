/**
 * 冲突审核区的服务端状态（TanStack Query）。
 * 约定：query key 以 `conflictKeys.all` 打头，hooks 只住本文件（票 11 在此追加待审队列与裁决）。
 */
export const conflictKeys = {
  all: ['conflicts'] as const,
}
