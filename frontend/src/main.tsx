import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createBrowserRouter } from 'react-router'

// 字体自托管（无外链 CDN）：Space Grotesk 在前，数字与英文自动走它；中文回落 Noto Sans SC。
// 只引 400 / 700 两档字重（风格文档第 5 节：正文常规 + 标题粗体）。
import '@fontsource/space-grotesk/latin-400.css'
import '@fontsource/space-grotesk/latin-700.css'
import '@fontsource/noto-sans-sc/latin-400.css'
import '@fontsource/noto-sans-sc/latin-700.css'
import '@fontsource/noto-sans-sc/chinese-simplified-400.css'
import '@fontsource/noto-sans-sc/chinese-simplified-700.css'

import './index.css'
import { AppProviders } from './app/providers'
import { routeObjects } from './app/router'

const router = createBrowserRouter(routeObjects)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
)
