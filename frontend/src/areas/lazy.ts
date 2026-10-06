import { lazy } from 'react'
import type { ComponentType, LazyExoticComponent } from 'react'

/**
 * 区级代码分割：把一个区的具名导出包成 `React.lazy` 组件。
 *
 * 为什么是「组件懒加载 + 注册表保持同步」而不是「注册表懒加载」：
 * 导航栏（AreaRail）、路由表与 `check:routes` 都要在启动时**同步**读到每区的
 * id / label / path / order / routes。所以注册表仍用 eager glob 汇总各区 `index.tsx`，
 * 但 `index.tsx` 只留一层极薄的懒壳（本函数）——区的真正实现连同它的依赖
 * （mermaid、elk、katex……）被 Vite 按区拆成独立 chunk，不再全部塞进 index chunk。
 *
 * Suspense 边界在 AppShell 的内容列：切换区时外壳不动，只有内容列显示加载态。
 */
export function lazyAreaModule(
  importer: () => Promise<unknown>,
  exportName: string,
): LazyExoticComponent<ComponentType> {
  return lazy(async () => {
    const module = (await importer()) as Record<string, unknown>
    return { default: module[exportName] as ComponentType }
  })
}
