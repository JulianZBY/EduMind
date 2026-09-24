/**
 * 备课会话区的服务端状态（TanStack Query）。
 *
 * 约定（票 04 为并行开发留缝）：本区全部 query key 以 `lessonPrepKeys.all` 打头，
 * hooks 一律住在本文件，不写进跨区共享的大文件——票 05/06 落地时只改本区目录。
 */
export const lessonPrepKeys = {
  all: ['lesson-prep'] as const,
}
