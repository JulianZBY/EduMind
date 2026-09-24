/**
 * 路由骨架自检：七条路由逐条可达、默认落脚区 = 备课会话、未知地址落到 404。
 *
 *   npm run check:routes
 *
 * 做法：用 Vite 的 ssrLoadModule 加载**真实**的区注册表与路由表（不是另抄一份断言表），
 * 再用 react-router 的 matchRoutes 逐条匹配。不需要浏览器、不需要起后端、不需要先构建；
 * 它跑的就是 src 里那份路由定义，所以任何一区漏挂路由都会在这里失败。
 */
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { RouterProvider, createMemoryRouter, matchRoutes } from 'react-router'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')

/** 票 04 的验收口径：六区 + 设置共七条一级路由，默认落在备课会话区。 */
const EXPECTED_AREAS = [
  { id: 'lesson-prep', path: '/lesson-prep', label: '备课会话', isDefault: true },
  { id: 'knowledge', path: '/knowledge', label: '知识库' },
  { id: 'artifacts', path: '/artifacts', label: '生成物' },
  { id: 'knowledge-graph', path: '/knowledge-graph', label: '知识图谱' },
  { id: 'conflicts', path: '/conflicts', label: '冲突审核' },
  { id: 'question-bank', path: '/question-bank', label: '题库' },
  { id: 'settings', path: '/settings', label: '设置' },
]

const failures = []
const check = (ok, message) => {
  if (ok) {
    console.log(`  ✓ ${message}`)
  } else {
    console.error(`  ✗ ${message}`)
    failures.push(message)
  }
}

const server = await createServer({
  root: frontendDir,
  configFile: resolve(frontendDir, 'vite.config.ts'),
  appType: 'custom',
  logLevel: 'error',
  // production 模式：与出包一致（import.meta.env.DEV=false，不挂 devtools）
  mode: 'production',
  server: { middlewareMode: true },
})

try {
  const registry = await server.ssrLoadModule('/src/areas/registry.ts')
  const routerModule = await server.ssrLoadModule('/src/app/router.tsx')

  const areas = registry.areas
  const routeObjects = routerModule.routeObjects
  const defaultAreaPath = registry.DEFAULT_AREA_PATH

  console.log(`路由骨架自检 · 注册表发现 ${areas.length} 个区`)
  check(areas.length === EXPECTED_AREAS.length, `区数量 = 7（实得 ${areas.length}）`)
  check(
    Array.isArray(routeObjects) && routeObjects.length === 1 && routeObjects[0].path === '/',
    '路由表以单根路由 / 承载全部区（外壳 + Outlet）',
  )

  const rootChildren = routeObjects[0].children ?? []
  const indexRoute = rootChildren.find((route) => route.index === true)
  check(Boolean(indexRoute), '根路由存在 index 子路由作为默认跳转')

  // 默认路由做成 loader 重定向，所以这里可以直接把「跳去哪」跑一遍：
  if (indexRoute && typeof indexRoute.loader === 'function') {
    const redirectResponse = await indexRoute.loader({})
    const location = redirectResponse.headers?.get('Location') ?? ''
    check(
      location.endsWith(defaultAreaPath),
      `默认路由 / 重定向到 ${defaultAreaPath}（实得 ${location || '未重定向'}）`,
    )
  } else {
    check(false, '默认路由由 index 路由的 loader 承担重定向')
  }

  check(defaultAreaPath === '/lesson-prep', `默认落脚区 = 备课会话（${defaultAreaPath}）`)

  const declaredDefaults = areas.filter((area) => area.isDefault)
  check(
    declaredDefaults.length === 1 && declaredDefaults[0].path === '/lesson-prep',
    '全站只有一个默认区，且是备课会话',
  )

  console.log('路由表：')
  for (const expected of EXPECTED_AREAS) {
    const area = areas.find((item) => item.id === expected.id)
    if (!area) {
      check(false, `区 ${expected.id} 已注册（${expected.label}）`)
      continue
    }
    check(area.path === expected.path, `区 ${expected.id} 的路径 = ${expected.path}`)
    check(area.label === expected.label, `区 ${expected.id} 的区名 = ${expected.label}`)

    const matches = matchRoutes(routeObjects, expected.path)
    const hit = matches?.some((match) => match.route.id === expected.id) ?? false
    check(hit, `${expected.path} → ${expected.label} 路由可达`)

    const children = (area.routes ?? []).flatMap((route) => route.children ?? [])
    console.log(
      `  · ${expected.path.padEnd(16)} ${expected.label}（${children.length} 条子路由：` +
        `${children.map((child) => (child.index ? 'index' : child.path)).join(' / ') || '无'}）`,
    )
  }

  const fallbackMatches = matchRoutes(routeObjects, '/no-such-area')
  const fallbackRoute = fallbackMatches?.at(-1)?.route
  check(fallbackRoute?.path === '*', '未知地址落到 * 兜底路由')

  const subRoutes = [
    { path: '/lesson-prep/session-123', expect: 'lesson-prep' },
    { path: '/knowledge/doc-123', expect: 'knowledge' },
    { path: '/artifacts/artifact-123', expect: 'artifacts' },
    { path: '/knowledge-graph/kp-123', expect: 'knowledge-graph' },
    { path: '/conflicts/conflict-123', expect: 'conflicts' },
    { path: '/question-bank/question-123', expect: 'question-bank' },
  ]
  for (const item of subRoutes) {
    const matches = matchRoutes(routeObjects, item.path)
    const hit = matches?.some((match) => match.route.id === item.expect) ?? false
    check(hit, `${item.path} → 选中对象可寻址（${item.expect}）`)
  }

  // 第三段：真渲染。用 react-dom/server 在 Node 里逐条渲染（无需浏览器），
  // 断言页面上真的出现了该区的区名 / 选中对象 / 兜底文案。
  const { AppProviders } = await server.ssrLoadModule('/src/app/providers.tsx')
  const renderCases = [
    ...EXPECTED_AREAS.map((area) => ({ path: area.path, expect: area.label })),
    { path: '/lesson-prep/session-abc', expect: 'session-abc' },
    { path: '/settings', expect: '供应商目录' },
    // 冲突审核的队列是服务端数据（票 11 起按类别取数），SSR 渲染时停在取数态，
    // 故这里断言面板自己的文案（带类别名）而不是空状态标题——它同样证明 ?category= 选中了该分区。
    { path: '/conflicts?category=structure', expect: '正在取「结构冲突」队列' },
    { path: '/no-such-area', expect: '这个地址不存在' },
  ]
  console.log('逐条渲染（react-dom/server，无浏览器；默认路由 / 的重定向已在上面的 loader 断言里跑过）：')
  for (const item of renderCases) {
    const router = createMemoryRouter(routeObjects, { initialEntries: [item.path] })
    const html = renderToStaticMarkup(
      createElement(AppProviders, null, createElement(RouterProvider, { router })),
    )
    check(html.includes(item.expect), `${item.path} 渲染出「${item.expect}」`)
  }
} finally {
  await server.close()
}

if (failures.length > 0) {
  console.error(`[check:routes] ${failures.length} 项未通过。`)
  process.exit(1)
}

console.log('[check:routes] 七条路由全部可达，默认路由 = 备课会话。')
