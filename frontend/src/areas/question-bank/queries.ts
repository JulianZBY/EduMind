/**
 * 题库区的服务端状态（TanStack Query）。
 * 约定：query key 以 `questionKeys.all` 打头，hooks 只住本文件（票 12 在此追加题目列表与筛选）。
 */
export const questionKeys = {
  all: ['question-bank'] as const,
}
