import type { ReactNode } from 'react'
import { ApiError } from '../../api/client'
import { FlatLoading } from '../../components/graph'
import { Badge, Button, Drawer } from '../../components/ui'
import { useKnowledgePoint } from './queries'

export interface KnowledgePointDrawerProps {
  /** 选中的知识点 id；为空即抽屉关闭。 */
  nodeId: string | null
  onClose: () => void
  /** 正在看的邻域跳数（null = 正在看全图）。 */
  neighborhoodDepth: number | null
  onExpandNeighborhood: (depth: number) => void
  onShowWholeGraph: () => void
}

/** 邻域可选跳数：与后端 `max_depth` 的 1–3 一致。 */
const DEPTH_CHOICES = [1, 2, 3] as const

function detailFailureText(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return '这个知识点已经不在图谱里了（可能被替换或删除）。关掉后重新打开图谱即可。'
  }
  return '读详情时出了点问题，关掉抽屉可以重试。'
}

/** 一句话说明难度与重要度，避免两个并排标签看不懂。 */
function difficultyLine(difficulty: string | null | undefined, importance: string | null | undefined): ReactNode {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge>{difficulty ?? '未标难度'}</Badge>
      {importance ? <Badge>{importance}</Badge> : null}
    </div>
  )
}

/**
 * 知识点详情抽屉：内容 / 难度 / 来源引用，并从这里展开邻域子图。
 * 抽屉的开合由路由（选中知识点）决定，故打开时数据一定在拉。
 */
export function KnowledgePointDrawer({
  nodeId,
  onClose,
  neighborhoodDepth,
  onExpandNeighborhood,
  onShowWholeGraph,
}: KnowledgePointDrawerProps) {
  const detail = useKnowledgePoint(nodeId)
  const point = detail.data

  const meta = [point?.subject, point?.chapter].filter(Boolean).join(' · ')

  return (
    <Drawer
      open={Boolean(nodeId)}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      title={point?.title ?? '知识点'}
      description={point ? meta || '未标学科与章节' : '正在读知识点详情…'}
      width="max-w-lg"
    >
      {detail.isPending ? <FlatLoading text="正在读知识点详情…" /> : null}

      {detail.isError ? (
        <div
          role="status"
          className="rounded-none border-2 border-[#ff3366] px-3 py-2 text-sm text-black"
        >
          <p className="font-bold">知识点详情没读出来</p>
          <p className="mt-1 text-xs text-black/60">{detailFailureText(detail.error)}</p>
        </div>
      ) : null}

      {point ? (
        <div className="flex flex-col gap-4">
          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-bold text-black/60">内容</h3>
            <p className="rounded-none border-2 border-black px-3 py-2 leading-6">{point.content}</p>
          </section>

          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-bold text-black/60">难度</h3>
            {difficultyLine(point.difficulty, point.importance)}
          </section>

          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-bold text-black/60">来源引用</h3>
            {point.sources.length === 0 ? (
              <p className="text-sm text-black/60">这个知识点还没有记录来源资料。</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {point.sources.map((source) => (
                  <li
                    key={source.doc_id}
                    className="flex flex-col gap-0.5 rounded-none border-2 border-black px-3 py-2"
                  >
                    <span className="text-sm">{source.filename ?? '资料名已不可用'}</span>
                    <span className="text-xs break-all text-black/60">{source.doc_id}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="flex flex-col gap-2 border-t-2 border-black pt-3">
            <h3 className="text-xs font-bold text-black/60">邻域</h3>
            <p className="text-sm text-black/60">
              从它出发向外看几跳：邻域子图会把上下游一起画出来（中心知识点用强调色描边）。
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {DEPTH_CHOICES.map((depth) => (
                <Badge
                  key={depth}
                  tone={neighborhoodDepth === depth ? 'accent' : 'outline'}
                  onClick={() => onExpandNeighborhood(depth)}
                  title={`以这个知识点为中心，向外 ${depth} 跳取子图`}
                >
                  {depth} 跳
                </Badge>
              ))}
              {neighborhoodDepth === null ? null : (
                <Button size="sm" onClick={onShowWholeGraph}>
                  返回全图
                </Button>
              )}
            </div>
          </section>
        </div>
      ) : null}
    </Drawer>
  )
}
