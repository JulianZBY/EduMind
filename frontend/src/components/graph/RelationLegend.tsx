import { cn } from '../../lib/cn'
import { ACCENT_COLOR, RELATION_STYLES } from './flowchart'

export interface RelationLegendProps {
  className?: string
}

/**
 * 关系图例：四种关系 → 线型与颜色（风格文档第 8 节那张表）。
 *
 * 线型与颜色直接读 `RELATION_STYLES`（画布也是它），图例与画布不会各说各话；
 * 颜色只有黑与强调色两种，虚线 / 粗线由 SVG 自绘，不用图片也不用图标字体。
 */
export function RelationLegend({ className }: RelationLegendProps) {
  return (
    <ul className={cn('flex flex-wrap items-center gap-x-4 gap-y-1', className)}>
      {RELATION_STYLES.map((style) => (
        <li key={style.relation} className="flex items-center gap-1.5 text-xs text-black">
          <svg aria-hidden="true" viewBox="0 0 40 10" width="40" height="10" className="shrink-0">
            <line
              x1="0"
              y1="5"
              x2="28"
              y2="5"
              stroke={style.color}
              strokeWidth={style.thick ? 3.5 : 2}
              strokeDasharray={style.dashed ? '5 3' : undefined}
            />
            <path d="M28 1 L38 5 L28 9 Z" fill={style.color} />
          </svg>
          <span>{style.relation}</span>
          <span className="text-black/60">
            {style.dashed ? '虚线' : style.thick ? '粗实线' : '实线'} ·{' '}
            {style.color === ACCENT_COLOR ? '强调色' : '黑'}
          </span>
        </li>
      ))}
    </ul>
  )
}
