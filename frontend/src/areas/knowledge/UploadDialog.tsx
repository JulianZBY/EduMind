/**
 * 上传教学资料弹层：选文件 + 可选参考资料标记，提交后立刻关闭并给出轻提示。
 *
 * 上传是「落盘 + 建记录 + 交后台解析」的即时动作（接口立即返回 `处理中`），
 * 因此弹层不承担进度：进度由列表与详情的轮询自动跟进（CONTEXT.md 第 4 节）。
 * 原生文件控件只做选择器过滤，皮肤由扁平按钮承担（风格文档第 2 节：零灰底、零圆角）。
 */
import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import { useToast } from '../../components/ui/useToast'
import { documentErrorMessage, useUploadDocument } from './queries'
import { useKnowledgeUi } from './store'

/**
 * 可选的文件后缀：与后端解析器注册表一致（`backend/app/knowledge/parsers/__init__.py`）。
 * 只影响系统选择器的过滤，不是校验——判不了的文件后端会落到「失败」终态。
 */
const ACCEPT =
  '.pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg,.mp4,.avi,.mov,.mp3,.wav,.m4a,.aac,.flac,.ogg,.oga,.opus,.wma,.amr'

export function UploadDialog() {
  const open = useKnowledgeUi((state) => state.uploadOpen)
  const closeUpload = useKnowledgeUi((state) => state.closeUpload)
  const [file, setFile] = useState<File | null>(null)
  const [isReference, setIsReference] = useState(false)
  const upload = useUploadDocument()
  const { toast } = useToast()

  function close() {
    setFile(null)
    setIsReference(false)
    upload.reset()
    closeUpload()
  }

  function submit() {
    if (!file) return
    upload.mutate(
      { file, isReference },
      {
        onSuccess: (created) => {
          toast({
            title: '资料已接收',
            description: `「${created.filename}」正在解析，状态会自动跟进到终态。`,
            tone: 'default',
          })
          close()
        },
      },
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) close()
      }}
      title="上传教学资料"
      description="PDF、Word、PPT、图片、视频、录音都可以；解析在后台进行，状态会自动跟进。"
      footer={
        <>
          <Button onClick={close} disabled={upload.isPending}>
            取消
          </Button>
          <Button variant="accent" onClick={submit} disabled={!file || upload.isPending}>
            {upload.isPending ? '上传中…' : '上传'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field
          htmlFor="knowledge-upload-file"
          label="选择文件"
          hint="解析会经过分块与入库；标记为参考资料后，备课检索会加权并在生成物中溯源。"
          error={upload.isError ? documentErrorMessage(upload.error) : undefined}
        >
          <div className="flex flex-wrap items-center gap-3">
            <Button
              asChild
              className="focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-black"
            >
              <label>
                <input
                  id="knowledge-upload-file"
                  type="file"
                  accept={ACCEPT}
                  className="sr-only"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
                选择文件
              </label>
            </Button>
            <span className="min-w-0 flex-1 truncate text-xs text-black/60">
              {file ? file.name : '还没有选择文件'}
            </span>
          </div>
        </Field>

        <div className="flex flex-col gap-1">
          <Button
            variant={isReference ? 'accent' : 'default'}
            aria-pressed={isReference}
            onClick={() => setIsReference((value) => !value)}
            className="self-start"
          >
            参考资料标记
          </Button>
          <p className="text-xs text-black/60">
            {isReference
              ? '已标记：备课时会检索加权，生成物里会溯源到这份资料。'
              : '未标记：仍可上传与检索，只是备课检索不额外加权。'}
          </p>
        </div>
      </div>
    </Dialog>
  )
}
