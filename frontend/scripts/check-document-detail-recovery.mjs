/** 离线来源恢复指引回归：渲染真实资料详情，使用 QueryClient 中的资料快照，不请求云端。 */
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createServer } from 'vite'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const server = await createServer({
  root: frontendDir,
  configFile: resolve(frontendDir, 'vite.config.ts'),
  appType: 'custom',
  logLevel: 'error',
  mode: 'production',
  server: { middlewareMode: true },
})

try {
  const { DocumentDetail } = await server.ssrLoadModule('/src/areas/knowledge/DocumentDetail.tsx')
  const { knowledgeKeys } = await server.ssrLoadModule('/src/areas/knowledge/queries.ts')

  function renderDetail({ fileType = '网页', source = '网页', reason = '', noteStatus = '未生成', status = '失败' } = {}) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const id = 'recovery-regression'
    client.setQueryData(knowledgeKeys.detail(id), {
      id, filename: '恢复指引回归', file_type: fileType,
      status, failure_reason: reason, is_reference: false,
      parsed_at: null, conflict_count: 0, chunk_count: 0, chunks: [],
      literature_note: { source, status: noteStatus, summary: '', knowledge_index: [] },
    })
    const html = renderToStaticMarkup(
      createElement(QueryClientProvider, { client },
        createElement(MemoryRouter, { initialEntries: [`/knowledge/${id}`] },
          createElement(Routes, null,
            createElement(Route, { path: '/knowledge/:documentId', element: createElement(DocumentDetail) }),
          ),
        ),
      ),
    )
    client.clear()
    return { html, text: html.replace(/<[^>]+>/g, '') }
  }

  for (const identity of [
    { fileType: '网页', source: '网页' },
    { fileType: '网页', source: '教学资料' },
    { fileType: 'pdf', source: '网页' },
  ]) {
    const { html, text } = renderDetail(identity)
    assert.ok(text.includes('备课会话') && text.includes('手动') && text.includes('联网检索并入库'), text)
    assert.ok(html.includes('href="/lesson-prep"'), html)
    assert.ok(!html.includes('重新上传'), html)
    assert.ok(html.includes('title="网页资料处理没有成功。请回到备课会话，手动再次点击「联网检索并入库」。"'), html)
  }

  const unconfigured = renderDetail({ reason: '分块能力未配置：请到设置页配置。' })
  assert.ok(unconfigured.text.includes('去设置'), unconfigured.text)
  assert.ok(unconfigured.text.includes('分块能力未配置'), unconfigured.text)
  assert.ok(!unconfigured.text.includes('重新上传'), unconfigured.text)

  const webNote = renderDetail({ noteStatus: '未配置', status: '已完成' })
  assert.ok(webNote.text.includes('去设置') && webNote.text.includes('联网检索并入库'), webNote.text)
  assert.ok(!webNote.text.includes('重新上传'), webNote.text)

  const uploaded = renderDetail({ fileType: 'pdf', source: '教学资料', reason: '解析失败，请重新上传。' })
  assert.ok(uploaded.text.includes('重新上传'), uploaded.text)
  assert.ok(!uploaded.html.includes('href="/lesson-prep"'), uploaded.html)
  assert.ok(uploaded.html.includes('title="解析没有成功，可按原文重新上传。"'), uploaded.html)
  const uploadNote = renderDetail({ fileType: 'pdf', source: '教学资料', noteStatus: '未配置', status: '已完成' })
  assert.ok(uploadNote.text.includes('配置后重新上传'), uploadNote.text)
  assert.ok(uploadNote.text.includes('去设置'), uploadNote.text)
  console.log('[check:document-detail-recovery] 网页／上传资料恢复分支、未配置设置引导全部通过。')
} finally {
  await server.close()
}
