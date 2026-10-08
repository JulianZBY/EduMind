/**
 * 冲突裁决 409 教师提示自检：两种 409（已裁决 vs 标题索引维度不兼容）必须给出不同且正确的提示。
 *
 *   npm run check:conflict-409
 *
 * 做法：用 Vite 的 ssrLoadModule 加载**真实**的 queries.ts（`conflictErrorMessage`）与 client.ts
 * （`ApiError`），构造两种 payload 调用真实函数。不需要浏览器、不需要起后端、不需要先构建。
 * 判别走的是稳定 `detail.code`（不是中文子串），所以这里用哨兵 message 也能证明分支正确。
 */
import { createServer } from 'vite'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')

// 与 backend/app/knowledge/vector_store.py::TITLE_INDEX_DIMENSION_MISMATCH_MESSAGE 及
// OpenAPI 409 示例保持一致的真实教师文案。
const REAL_DIMENSION_MESSAGE =
  '这条冲突仍保持待审：标题索引与当前设置不兼容，需要先处理标题索引，处理完成后再裁决这条冲突；知识图谱没有变化。'

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
  mode: 'production',
  server: { middlewareMode: true },
})

try {
  const { conflictErrorMessage } = await server.ssrLoadModule(
    '/src/areas/conflicts/queries.ts',
  )
  const { ApiError } = await server.ssrLoadModule('/src/api/client.ts')

  const reviewed = new ApiError(409, { detail: '该冲突已审核: 已接受' })
  const reviewedMessage = conflictErrorMessage(reviewed)
  check(
    reviewedMessage === '这条冲突已经裁决过，不能重复提交。',
    `已裁决 409 保持原提示（实得「${reviewedMessage}」）`,
  )

  const dimension = new ApiError(409, {
    detail: { code: 'title_index_dimension_mismatch', message: REAL_DIMENSION_MESSAGE },
  })
  const dimensionMessage = conflictErrorMessage(dimension)
  check(dimensionMessage === REAL_DIMENSION_MESSAGE, '维度 409 显示后端面向教师的消息')
  check(dimensionMessage.includes('待审'), '维度 409 提示说明仍保持待审')
  check(dimensionMessage.includes('标题索引'), '维度 409 提示说明标题索引需先处理')
  check(
    !dimensionMessage.includes('已裁决') && !dimensionMessage.includes('重复提交'),
    '维度 409 不误报为已裁决 / 重复提交',
  )
  check(!dimensionMessage.includes('重建'), '维度 409 不引导不存在的重建按钮')

  check(reviewedMessage !== dimensionMessage, '两种 409 的提示不同')

  // 哨兵消息：证明分支看的是稳定 code，而不是中文子串（哨兵不含任何提示词，仍走维度分支）。
  const sentinel = new ApiError(409, {
    detail: { code: 'title_index_dimension_mismatch', message: 'SENTINEL-MESSAGE' },
  })
  check(
    conflictErrorMessage(sentinel) === 'SENTINEL-MESSAGE',
    '维度 409 按 detail.code 判别（哨兵 message 仍正确路由，非中文子串匹配）',
  )
} finally {
  await server.close()
}

if (failures.length > 0) {
  console.error(`[check:conflict-409] ${failures.length} 项未通过。`)
  process.exit(1)
}

console.log('[check:conflict-409] 两种 409 的教师提示不同且正确。')
