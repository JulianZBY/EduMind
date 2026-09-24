import { useUiStore } from '../../store/ui'
import type { ToastMessage } from '../../store/ui'

/**
 * 触发轻提示：`toast({ title, description, tone })`。
 * 队列本身住在 zustand（见 src/store/ui.ts），这里只给出调用形状。
 */
export function useToast(): { toast: (toast: Omit<ToastMessage, 'id'>) => string } {
  const pushToast = useUiStore((state) => state.pushToast)
  return { toast: pushToast }
}
