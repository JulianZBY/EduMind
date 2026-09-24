import { Outlet, useSearchParams } from 'react-router'
import { AreaStub } from '../../components/layout/AreaStub'
import { MainPanel } from '../../components/layout/Workbench'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/Tabs'
import { ConflictQueuePanel } from './ConflictQueuePanel'
import { CATEGORY_SLUGS, CONFLICT_CATEGORIES, categoryFromSlug } from './actions'
import type { ConflictCategory } from './actions'

/**
 * 冲突审核区（CONTEXT.md 第 6 节）。三类别**分区呈现**，各自有专属形态与动作：
 * 定义冲突 = 新旧对照卡片（三选一）；结构冲突 = 再加「图谱现状 vs 三种裁决终态」的小图（三选一）；
 * 常识存疑 = 红旗标记 + 原文（两选一 + 编辑修正后入库）。
 *
 * 类别用搜索参数寻址（`/conflicts?category=structure`），刷新与分享不丢上下文，切换不制造历史记录。
 */
const CATEGORY_TEXT: Record<
  ConflictCategory,
  { emptyTitle: string; emptyDescription: string; note: string }
> = {
  定义冲突: {
    emptyTitle: '没有待审的定义冲突',
    emptyDescription:
      '同一个知识点出现两段互相矛盾的描述时，这里给出新旧对照卡片，等你三选一。',
    note: '检测已就位：解析资料时会比对同名与近名知识点，两段描述矛盾即进待审队列，图谱里先不放新知。',
  },
  结构冲突: {
    emptyTitle: '没有待审的结构冲突',
    emptyDescription:
      '新知识在层级或依赖关系上与图谱现状打架时，这里给出「图谱现状 vs 三种裁决终态」的小图，等你三选一。',
    note: '检测尚未实现（ADR-0006）：这里呈现的是裁决动作与三张终态图，队列里出现结构冲突要等检测落地。',
  },
  常识存疑: {
    emptyTitle: '没有待审的常识存疑',
    emptyDescription:
      '内容可能是错的常识时，这里给出红旗标记与原文，等你决定照常入库、拒绝，还是编辑修正后入库。',
    note: '检测尚未实现（ADR-0006）：这里呈现的是裁决动作与原文对照，队列里出现常识存疑要等检测落地。',
  },
}

/** 冲突审核区：主区直铺队列（按类别分区）。 */
export function ConflictsArea() {
  return (
    <MainPanel title="冲突审核" tagline="新知识进库前，教师裁决矛盾的地方">
      <Outlet />
    </MainPanel>
  )
}

/** 队列：三个类别各一个分区，分区内容是该类别的裁决卡列表。 */
export function ConflictsQueue() {
  const [searchParams, setSearchParams] = useSearchParams()
  const active = categoryFromSlug(searchParams.get('category'))

  return (
    <Tabs
      value={CATEGORY_SLUGS[active]}
      onValueChange={(slug) => setSearchParams({ category: slug }, { replace: true })}
      className="flex min-h-0 flex-1 flex-col"
    >
      <TabsList>
        {CONFLICT_CATEGORIES.map((category) => (
          <TabsTrigger key={category} value={CATEGORY_SLUGS[category]}>
            {category}
          </TabsTrigger>
        ))}
      </TabsList>
      {CONFLICT_CATEGORIES.map((category) => (
        <TabsContent key={category} value={CATEGORY_SLUGS[category]}>
          <ConflictQueuePanel
            category={category}
            emptyTitle={CATEGORY_TEXT[category].emptyTitle}
            emptyDescription={CATEGORY_TEXT[category].emptyDescription}
            note={CATEGORY_TEXT[category].note}
          />
        </TabsContent>
      ))}
    </Tabs>
  )
}

export function ConflictsDetail() {
  return (
    <AreaStub
      title="冲突已选中"
      description="新旧知识对照与裁决动作在队列卡片里展开；这里只保证路由可寻址。"
      paramKey="conflictId"
      objectLabel="冲突"
    />
  )
}
