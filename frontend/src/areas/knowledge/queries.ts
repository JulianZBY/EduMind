/**
 * 知识库区的服务端状态（TanStack Query）。
 * 约定：query key 以 `knowledgeKeys.all` 打头，hooks 只住本文件（票 09 在此追加资料列表与详情）。
 */
export const knowledgeKeys = {
  all: ['knowledge'] as const,
}
