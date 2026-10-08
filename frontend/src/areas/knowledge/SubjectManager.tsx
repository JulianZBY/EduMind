import { useState } from 'react'
import type { SubjectView } from '../../api/generated'
import { apiErrorMessage } from '../../api/client'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { Input } from '../../components/ui/Input'
import { useCreateSubject, useDeleteSubject, useRenameSubject, useSubjects } from './queries'

/** 学科维护留在知识库区；不占用冲突审核，不包含新学科提议。 */
export function SubjectManager() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>管理学科</Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="学科清单"
        description="知识点只有一个主学科。无法从清单选择时归「未分类」，跨学科联系用「相关关联」表达。"
      >
        {open ? <SubjectList /> : null}
      </Dialog>
    </>
  )
}

function SubjectList() {
  const subjects = useSubjects(true)
  const create = useCreateSubject()
  const [name, setName] = useState('')
  return (
    <div className="flex flex-col gap-3">
      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          create.mutate({ name: name.trim() }, { onSuccess: () => setName('') })
        }}
      >
        <label className="flex-1">
          <span className="block text-xs font-bold">新学科名称</span>
          <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} required disabled={create.isPending} />
        </label>
        <Button type="submit" disabled={create.isPending || !name.trim()}>
          {create.isPending ? '正在新增…' : '新增学科'}
        </Button>
      </form>
      {create.isError ? <ErrorNotice error={create.error} /> : null}
      {subjects.isPending ? <p className="text-black/60">正在读取学科清单…</p> : null}
      {subjects.isError ? (
        <div className="rounded-none border-2 border-black p-3">
          <ErrorNotice error={subjects.error} />
          <Button onClick={() => subjects.refetch()}>重试</Button>
        </div>
      ) : null}
      {subjects.data?.subjects.length === 0 ? <p>清单为空，请新增学科。</p> : null}
      <ul className="flex flex-col gap-2">
        {subjects.data?.subjects.map((subject) => (
          <li key={`${subject.id}:${subject.name}`} className="rounded-none border-2 border-black p-2">
            {subject.name === '未分类' ? (
              <p>未分类<span className="ml-2 text-xs text-black/60">归类兜底，不能更名或删除。</span></p>
            ) : <SubjectRow subject={subject} />}
          </li>
        ))}
      </ul>
      <p className="text-xs text-black/60">更名会同步更新知识点；删除学科后，其知识点归「未分类」，知识点与关系不删除。新增学科不会自动重新归类已有知识点。</p>
    </div>
  )
}

function SubjectRow({ subject }: { subject: SubjectView }) {
  const [name, setName] = useState(subject.name)
  const [confirm, setConfirm] = useState(false)
  const rename = useRenameSubject()
  const remove = useDeleteSubject()
  const busy = rename.isPending || remove.isPending
  return (
    <>
      <form
        className="flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          rename.mutate({ subjectId: subject.id, body: { name: name.trim() } })
        }}
      >
        <Input aria-label={`学科名称：${subject.name}`} value={name} onChange={(event) => setName(event.target.value)} maxLength={100} required disabled={busy} />
        <Button size="sm" type="submit" disabled={busy || !name.trim() || name.trim() === subject.name}>保存</Button>
        <Button size="sm" disabled={busy} onClick={() => { remove.reset(); setConfirm(true) }}>删除</Button>
      </form>
      {rename.isError ? <ErrorNotice error={rename.error} /> : null}
      <Dialog
        open={confirm}
        onOpenChange={(value) => { if (!remove.isPending) setConfirm(value) }}
        title={`删除学科「${subject.name}」？`}
        description="这会将该学科的知识点归「未分类」，不会删除知识点或关系。"
        footer={
          <>
            <Button disabled={remove.isPending} onClick={() => setConfirm(false)}>取消</Button>
            <Button variant="accent" disabled={remove.isPending} onClick={() => remove.mutate(subject.id, { onSuccess: () => setConfirm(false) })}>
              {remove.isPending ? '正在删除…' : '确认删除'}
            </Button>
          </>
        }
      >
        {remove.isError ? <ErrorNotice error={remove.error} /> : <p>删除后，后续入库也不再使用这个学科。</p>}
      </Dialog>
    </>
  )
}

function ErrorNotice({ error }: { error: unknown }) {
  return <p role="alert" className="my-2 rounded-none border-2 border-[#ff3366] p-2 text-black">{apiErrorMessage(error, '学科清单没有读出来，请稍后重试。')}</p>
}
