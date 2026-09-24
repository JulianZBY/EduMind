import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent, MouseEvent } from 'react'
import { cn } from '../../lib/cn'
import { FlatLoading } from './FlatLoading'
import { flatThemeSource, makeNodesFocusable, mermaidNodeIdFromDomId, sharpenLinkCorners } from './flowchart'

export interface FlatMermaidProps {
  /** mermaid 源码；没自带 init 指令时组件会补上扁平主题（第 8 节配方）。 */
  source: string
  /** 点击节点：参数是 mermaid 源码里的节点名（配 `buildFlowchartSource` 的 `nodeIdByMermaidId` 翻回业务 id）。 */
  onNodeClick?: (mermaidNodeId: string) => void
  /** 图的用途说明：无障碍标签，供读屏与排查用。 */
  label?: string
  /** 渲染失败时面向教师的一句处置建议。 */
  errorHint?: string
  className?: string
}

type RenderStatus = 'loading' | 'ready' | 'failed'

/** 节点名 → 业务 id：mermaid 画的节点用 `flowchart-<节点名>-<序号>` 做 domId。 */
function nodeNameOf(eventTarget: EventTarget | null): string | null {
  if (!(eventTarget instanceof Element)) return null
  return mermaidNodeIdFromDomId(eventTarget.closest('g.node')?.getAttribute('id') ?? '')
}

/**
 * mermaid 渲染器（扁平皮肤）：把 mermaid 源码画成白底黑框的图。
 *
 * - 主题、线型、节点黑边全部来自 `flowchart.ts`（第 8 节配方的唯一实现），本组件只管渲染；
 * - mermaid 需要真实 DOM 量文字，故**动态加载**：服务端渲染不会走到它，页面不会因它崩；
 * - 加载态用「文字 + 直角进度条」，失败态用强调色边框 + 文案，都不退回浏览器默认样式；
 * - 节点点击用事件委托：mermaid 生成的节点 domId 形如 `flowchart-<节点名>-<序号>`。
 */
export function FlatMermaid({
  source,
  onNodeClick,
  label = '图谱',
  errorHint = '可以刷新重试；若反复失败，请检查知识点数据是否完整。',
  className,
}: FlatMermaidProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const instanceId = useId()
  const [status, setStatus] = useState<RenderStatus>('loading')
  const [error, setError] = useState<string | null>(null)
  const renderSeq = useRef(0)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let cancelled = false
    renderSeq.current += 1
    const renderId = `edumind-${instanceId.replace(/[^\w-]/g, '')}-${renderSeq.current}`

    void (async () => {
      try {
        const mermaid = (await import('mermaid')).default
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' })
        const rendered = await mermaid.render(renderId, flatThemeSource(source))
        if (cancelled) return
        // 唯一一处把 mermaid 产出放进 DOM 的地方：
        // mermaid 在 securityLevel=strict 下已用 DOMPurify 洗过它产出的 svg（见其 renderDiagram），
        // 且数据源是本仓库自己的知识点库；这里用 DOM 解析 API 插入，不用 innerHTML 一类注入点。
        // `sharpenLinkCorners` 把连线转角还原成直角（见 flowchart.ts）。
        const fragment = document
          .createRange()
          .createContextualFragment(sharpenLinkCorners(rendered.svg))
        container.replaceChildren(fragment)
        makeNodesFocusable(container)
        setError(null)
        setStatus('ready')
      } catch (cause) {
        if (cancelled) return
        container.replaceChildren()
        setError(cause instanceof Error ? cause.message : '渲染失败')
        setStatus('failed')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [instanceId, source])

  const handleClick = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      if (!onNodeClick) return
      const nodeName = nodeNameOf(event.target)
      if (nodeName) onNodeClick(nodeName)
    },
    [onNodeClick],
  )

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (!onNodeClick || (event.key !== 'Enter' && event.key !== ' ')) return
      const nodeName = nodeNameOf(event.target)
      if (!nodeName) return
      event.preventDefault()
      onNodeClick(nodeName)
    },
    [onNodeClick],
  )

  return (
    <div className={cn('flex min-w-0 flex-col gap-2', className)}>
      {status === 'loading' ? <FlatLoading text="正在画图谱…" /> : null}

      {status === 'failed' ? (
        <div role="status" className="rounded-none border-2 border-[#ff3366] px-3 py-2 text-sm text-black">
          <p className="font-bold">图谱没能画出来</p>
          <p className="mt-1 text-xs text-black/60">{errorHint}</p>
          <p className="mt-1 text-xs break-all text-black/60">失败原因：{error}</p>
        </div>
      ) : null}

      <div
        ref={containerRef}
        role="img"
        aria-label={label}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        className={cn(
          'min-w-0 overflow-auto rounded-none',
          onNodeClick ? '[&_g.node]:cursor-pointer' : '',
        )}
      />
    </div>
  )
}
