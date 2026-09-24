/**
 * 全局界面状态（zustand）：只放**跨组件**的界面状态。
 *
 * 纪律（ADR-0005 / 票 04）：
 * - 服务端数据一律走 TanStack Query，不进这里，也不在浏览器里存第二份事实源；
 * - 组件内部的局部状态（一次开关、一段输入）用 useState，不要图省事塞进来；
 * - 区内专属的界面状态放各区自己的 `src/areas/<area>/store.ts`（票 06 起按需新增）。
 */
import { create } from 'zustand'

export type ToastTone = 'default' | 'accent'

export interface ToastMessage {
  readonly id: string
  readonly title: string
  readonly description?: string
  /** accent = 强调色边框：用于失败、危险与需要教师注意的提示（不用红绿蓝）。 */
  readonly tone: ToastTone
}

interface UiState {
  /** 区级导航栏折叠（工作台密度下的一屏多信息）。 */
  railCollapsed: boolean
  toggleRail: () => void
  /** 服务状态抽屉：由顶栏按钮打开，由外壳渲染，故属于跨组件界面状态。 */
  servicePanelOpen: boolean
  setServicePanelOpen: (open: boolean) => void
  /** 关于弹层：同样由顶栏按钮打开、由外壳渲染。 */
  aboutOpen: boolean
  setAboutOpen: (open: boolean) => void
  toasts: ToastMessage[]
  pushToast: (toast: Omit<ToastMessage, 'id'>) => string
  dismissToast: (id: string) => void
}

let toastSeq = 0

export const useUiStore = create<UiState>((set) => ({
  railCollapsed: false,
  toggleRail: () => set((state) => ({ railCollapsed: !state.railCollapsed })),
  servicePanelOpen: false,
  setServicePanelOpen: (open) => set({ servicePanelOpen: open }),
  aboutOpen: false,
  setAboutOpen: (open) => set({ aboutOpen: open }),
  toasts: [],
  pushToast: (toast) => {
    toastSeq += 1
    const id = `toast-${toastSeq}`
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }))
    return id
  },
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((item) => item.id !== id) })),
}))
