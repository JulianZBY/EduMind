import type { AreaModule } from './types'

/**
 * 区注册表——**只做汇总，不含任何一区的具体内容**。
 *
 * 汇总方式是 import.meta.glob 自动发现 `src/areas/<area>/index.tsx`：
 * 新增一区只需新建那个目录并默认导出 AreaModule，本文件一行都不用改，
 * 因此后续票 09/10/12/13 并行开分支时不会在共享文件上撞车。
 *
 * 若注册表本身有问题（缺 id、路径重复、默认区不唯一），就在这里快速失败：
 * 配错的骨架应该在启动时就报出来，而不是等点到某个区才发现。
 */
const discovered = import.meta.glob<{ default: AreaModule }>('./*/index.tsx', { eager: true })

function collectAreas(): AreaModule[] {
  const modules = Object.entries(discovered)
    .map(([file, module]) => ({ file, area: module.default }))
    .sort((a, b) => a.file.localeCompare(b.file))

  const areas = modules.map(({ file, area }) => {
    if (!area) {
      throw new Error(`区注册失败：${file} 没有默认导出 AreaModule`)
    }
    if (!area.id || !area.label || !area.path || typeof area.order !== 'number') {
      throw new Error(`区注册失败：${file} 缺少 id / label / path / order`)
    }
    if (!Array.isArray(area.routes) || area.routes.length === 0) {
      throw new Error(`区注册失败：${area.id} 没有路由（每区必须导出自己的 routes）`)
    }
    if (!area.routes.some((route) => route.id === area.id)) {
      throw new Error(`区注册失败：${area.id} 的 routes 里缺少 id 为 "${area.id}" 的顶层路由`)
    }
    return area
  })

  const paths = new Set<string>()
  const ids = new Set<string>()
  for (const area of areas) {
    if (paths.has(area.path)) throw new Error(`区注册失败：路径重复 ${area.path}`)
    if (ids.has(area.id)) throw new Error(`区注册失败：id 重复 ${area.id}`)
    paths.add(area.path)
    ids.add(area.id)
  }

  const defaults = areas.filter((area) => area.isDefault)
  if (defaults.length !== 1) {
    throw new Error(`区注册失败：默认落脚区必须唯一，当前 ${defaults.length} 个`)
  }

  return areas.sort((a, b) => a.order - b.order)
}

/** 按导航顺序排列的全部区（六区 + 设置）。 */
export const areas: AreaModule[] = collectAreas()

/** 默认落脚区：备课会话。 */
export const DEFAULT_AREA: AreaModule = areas.find((area) => area.isDefault) ?? areas[0]

/** 默认路由路径：根路径 `/` 与未知地址的兜底跳转目标。 */
export const DEFAULT_AREA_PATH: string = DEFAULT_AREA.path
