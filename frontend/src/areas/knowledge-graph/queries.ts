/**
 * 知识图谱区的服务端状态（TanStack Query）。
 * 约定：query key 以 `graphKeys.all` 打头，hooks 只住本文件（票 10 在此追加图谱 / 过滤 / 邻域）。
 */
export const graphKeys = {
  all: ['knowledge-graph'] as const,
}
