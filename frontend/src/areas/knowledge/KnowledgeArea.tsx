/**
 * 知识库区（CONTEXT.md 第 1 节）：教师个人教学资料的仓库。
 *
 * 形态：二级侧栏（资料列表，工作台密度）+ 主区（资料详情 / 空状态，编辑密度）。
 * 侧栏的列表是整个区的「状态跟进面板」：还有资料在解析就自动轮询，
 * 全部落终态即停——全程不需要教师点刷新。
 */
import { Outlet } from 'react-router'
import type { ReactNode } from 'react'
import type { DocumentView } from '../../api/generated'
import { EmptyState } from '../../components/ui/EmptyState'
import { Button } from '../../components/ui/Button'
import { MainPanel, Workbench, WorkbenchSidebar } from '../../components/layout/Workbench'
import { DocumentDetail } from './DocumentDetail'
import { DocumentsSidebar } from './DocumentList'
import { UploadDialog } from './UploadDialog'
import { isProcessing } from './status'
import { useDocuments } from './queries'
import { useKnowledgeUi } from './store'

export function KnowledgeArea() {
  const { data, isPending, isError } = useDocuments()
  const openUpload = useKnowledgeUi((state) => state.openUpload)
  const documents = data?.documents ?? []

  return (
    <Workbench
      sidebar={
        <WorkbenchSidebar
          title="资料列表"
          meta={<DocumentsMeta documents={documents} isPending={isPending} isError={isError} />}
          actions={
            <Button size="sm" onClick={openUpload}>
              上传资料
            </Button>
          }
        >
          <DocumentsSidebar documents={documents} isPending={isPending} isError={isError} />
        </WorkbenchSidebar>
      }
    >
      <MainPanel title="知识库" tagline="教师个人教学资料的仓库">
        <Outlet />
      </MainPanel>
      <UploadDialog />
    </Workbench>
  )
}

/** 侧栏计数：一眼看出「几份资料、几份还在解析」。 */
function DocumentsMeta({
  documents,
  isPending,
  isError,
}: {
  documents: readonly DocumentView[]
  isPending: boolean
  isError: boolean
}): ReactNode {
  if (isPending) return '读取中…'
  if (isError) return '未读出'
  const processing = documents.filter((document) => isProcessing(document.status)).length
  return processing
    ? `${documents.length} 份资料 · ${processing} 份处理中`
    : `${documents.length} 份资料`
}

/** 主区默认页：列表的加载 / 错误 / 空 / 未选中四态，全部按编辑密度（大留白、单列窄容器）。 */
export function KnowledgeIndex() {
  const { data, isPending, isError, refetch } = useDocuments()
  const openUpload = useKnowledgeUi((state) => state.openUpload)
  const documents = data?.documents ?? []

  if (isPending) {
    return <p className="px-3 py-12 text-center text-sm text-black/60">正在读取资料列表…</p>
  }

  if (isError) {
    return (
      <EmptyState
        title="资料列表没有读出来"
        description="接口没有返回资料列表：可能是服务暂时不可用。修好后点重试，不必重新上传。"
        action={
          <Button variant="accent" onClick={() => refetch()}>
            重试
          </Button>
        }
      />
    )
  }

  if (documents.length === 0) {
    return (
      <EmptyState
        title="还没有教学资料"
        description="上传 PDF、Word、PPT、图片、视频或录音后，解析状态会显示在左列并从「处理中」自动跟进到终态。"
        action={
          <Button variant="accent" onClick={openUpload}>
            上传资料
          </Button>
        }
      />
    )
  }

  const processing = documents.filter((document) => isProcessing(document.status)).length
  return (
    <EmptyState
      title="还没有选中教学资料"
      description="左列按解析状态跟进每一份资料；选中一份资料，这里显示解析结果与入库的分块。"
      meta={
        processing
          ? `${documents.length} 份资料，其中 ${processing} 份正在解析`
          : `${documents.length} 份资料`
      }
    />
  )
}

/** 选中一份资料：URL 即路由（`/knowledge/:documentId`），详情按 id 取。 */
export function KnowledgeDocument() {
  return <DocumentDetail />
}
