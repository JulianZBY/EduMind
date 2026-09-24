import { Outlet, useSearchParams } from 'react-router'
import { AreaStub } from '../../components/layout/AreaStub'
import { MainPanel } from '../../components/layout/Workbench'
import { EmptyState } from '../../components/ui/EmptyState'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/Tabs'

/**
 * 冲突三类别（CONTEXT.md 第 6 节）。类别用搜索引擎参数寻址（`/conflicts?category=structure`），
 * 刷新与分享不丢上下文，切换不制造历史记录。
 *
 * 文案纪律（CONTEXT.md 第 6 节 / ADR-0004）：结构冲突与常识存疑的**检测逻辑尚未实现**，
 * 文案只描述裁决动作与形态，不承诺能自动发现这两类冲突。
 */
const CATEGORIES = [
  {
    value: 'definition',
    label: '定义冲突',
    emptyTitle: '没有待审的定义冲突',
    description: '同一个知识点出现两段互相矛盾的描述时，这里给出新旧对照卡片，等你三选一。',
  },
  {
    value: 'structure',
    label: '结构冲突',
    emptyTitle: '没有待审的结构冲突',
    description: '结构冲突的裁决动作是三选一：接受新 / 保留旧 / 并存。检测尚未实现，本区只呈现裁决形态与图谱终态。',
  },
  {
    value: 'common-sense',
    label: '常识存疑',
    emptyTitle: '没有待审的常识存疑',
    description:
      '常识存疑的裁决动作是照常入库 / 拒绝，另可编辑修正后入库。检测尚未实现，本区只呈现裁决形态与原文对照。',
  },
] as const

/** 冲突审核区：主区直铺队列（按类别分区）。票 11 在此长出三类别各自形态。 */
export function ConflictsArea() {
  return (
    <MainPanel title="冲突审核" tagline="新知识进库前，教师裁决矛盾的地方">
      <Outlet />
    </MainPanel>
  )
}

export function ConflictsQueue() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('category')
  const active = CATEGORIES.find((category) => category.value === requested)?.value ?? CATEGORIES[0].value

  return (
    <Tabs
      value={active}
      onValueChange={(value) => setSearchParams({ category: value }, { replace: true })}
      className="flex flex-col"
    >
      <TabsList>
        {CATEGORIES.map((category) => (
          <TabsTrigger key={category.value} value={category.value}>
            {category.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {CATEGORIES.map((category) => (
        <TabsContent key={category.value} value={category.value}>
          <EmptyState title={category.emptyTitle} description={category.description} />
        </TabsContent>
      ))}
    </Tabs>
  )
}

export function ConflictsDetail() {
  return (
    <AreaStub
      title="冲突已选中"
      description="新旧知识对照与裁决动作在这里展开；当前只保证路由可寻址。"
      paramKey="conflictId"
      objectLabel="冲突"
    />
  )
}
