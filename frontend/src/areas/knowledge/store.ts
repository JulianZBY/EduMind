/**
 * 知识库区专属的界面状态（zustand）：只放**跨组件**、且不属于服务端数据的东西。
 *
 * 这里只有一件事——上传弹层的开合。它必须共享：侧栏的「上传资料」、空状态里的
 * 「上传资料」、失败资料详情里的「重新上传」都要唤起同一个弹层，而弹层只渲染一份。
 * 弹层里的「选了哪个文件 / 是否标记参考资料」是局部输入，用 useState 就够，不进这里。
 */
import { create } from 'zustand'

interface KnowledgeUiState {
  uploadOpen: boolean
  openUpload: () => void
  closeUpload: () => void
}

export const useKnowledgeUi = create<KnowledgeUiState>((set) => ({
  uploadOpen: false,
  openUpload: () => set({ uploadOpen: true }),
  closeUpload: () => set({ uploadOpen: false }),
}))
