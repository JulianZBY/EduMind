/**
 * 设置区：单页表单、编辑密度（一次只做一件事）。
 *
 * 四张卡各管一段：供应商（多供应商并存，只加家不选模型）/ 全局默认（从统一模型池选一个
 * 具体模型）/ 任务级模型（每个任务从统一模型池选模型，默认跟随全局）/ 能力实现。
 * 模型清单在添加供应商时自动拉取并缓存，设置页展示的统一模型池 = 所有已添加供应商的
 * 模型合并（每条标注来自哪家）。Key 只有掩码会出现在响应里，输入框里的明文只来自教师粘贴。
 */
import { useState } from 'react'
import type { ReactNode } from 'react'

import { MainPanel } from '../../components/layout/Workbench'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardFooter, CardHeader } from '../../components/ui/Card'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'
import { useToast } from '../../components/ui/useToast'
import { AddProviderDialog } from './AddProviderDialog'
import { OptionPicker } from './OptionPicker'
import type { PickerOption } from './OptionPicker'
import {
  settingsErrorMessage,
  settingsPatch,
  useDeleteProviderInstance,
  useRefreshProviderModels,
  useSettingsCatalogQuery,
  useSettingsQuery,
  useUpdateProviderInstance,
  useUpdateSettings,
} from './queries'
import type { SettingsCatalogBody, SettingsViewBody } from './queries'

/** 统一模型池里的一条：模型 + 来自哪家（同名不同家 = 两条独立条目，走各家的 Key）。 */
interface PoolEntry {
  instanceId: string
  instanceLabel: string
  model: string
}

/** 选择器的取值编码：`<实例id>::<模型>`；「跟随全局」与「手动填写」是保留值。 */
const FOLLOW_GLOBAL = 'follow-global'
const MANUAL_MODEL = 'manual-model'

function poolOf(view: SettingsViewBody): PoolEntry[] {
  return view.provider_instances.flatMap((instance) =>
    instance.models.map((model) => ({
      instanceId: instance.id,
      instanceLabel: instance.label,
      model,
    })),
  )
}

function poolOption(entry: PoolEntry): PickerOption {
  return { id: `${entry.instanceId}::${entry.model}`, label: entry.model, note: entry.instanceLabel }
}

export function SettingsArea() {
  const settings = useSettingsQuery()
  const catalog = useSettingsCatalogQuery()

  if (settings.isPending || catalog.isPending) {
    // 加载态也先把第一张卡的标题立起来：页面结构立刻可见，不是一片空白。
    return (
      <MainPanel title="设置" tagline="云端能力与模型档位的配置页">
        <div className="mx-auto flex w-full max-w-xl flex-col gap-4 px-6 py-8">
          <Card>
            <CardHeader title="供应商" meta="可同时添加多家" />
            <CardBody className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-none border-2 border-black"
              />
              <p className="text-sm text-black/60">正在读取设置…</p>
            </CardBody>
          </Card>
        </div>
      </MainPanel>
    )
  }

  if (settings.isError || catalog.isError) {
    return (
      <MainPanel title="设置" tagline="云端能力与模型档位的配置页">
        <div className="mx-auto flex w-full max-w-xl flex-col gap-4 px-6 py-8">
          <Card>
            <CardHeader title="读取设置失败" meta="没有改动任何设置" />
            <CardBody className="flex flex-col gap-3">
              <p className="flex items-start gap-2 text-sm leading-6 text-[#ff3366]">
                <span aria-hidden="true" className="mt-2 h-2 w-2 shrink-0 bg-[#ff3366]" />
                {settingsErrorMessage(settings.error ?? catalog.error)}
              </p>
              <Button
                onClick={() => {
                  void settings.refetch()
                  void catalog.refetch()
                }}
              >
                重试
              </Button>
            </CardBody>
          </Card>
        </div>
      </MainPanel>
    )
  }

  return (
    <MainPanel title="设置" tagline="云端能力与模型档位的配置页">
      <div className="mx-auto flex w-full max-w-xl flex-col gap-4 px-6 py-8">
        <ProviderListPanel view={settings.data} catalog={catalog.data} />
        <GlobalDefaultPanel view={settings.data} />
        <TaskModelPanel view={settings.data} />
        <CapabilityPanel view={settings.data} catalog={catalog.data} />
        <p className="text-xs leading-5 text-black/60">{settings.data.note}</p>
      </div>
    </MainPanel>
  )
}

/**
 * 草稿层：未改过的项回落到服务端生效值（稀疏覆盖）。
 * 写入成功后视图对象换新（PUT 的响应回填缓存），草稿层随渲染作废——避免旧草稿把新值覆盖回去。
 */
function useDrafts(view: SettingsViewBody) {
  const [snapshot, setSnapshot] = useState<{ view: SettingsViewBody; drafts: Record<string, string> }>(
    { view, drafts: {} },
  )
  const drafts = snapshot.view === view ? snapshot.drafts : {}
  return {
    valueOf: (key: string, fallback: string) => drafts[key] ?? fallback,
    setValue: (key: string, value: string) =>
      setSnapshot({ view, drafts: { ...drafts, [key]: value } }),
  }
}

/** 一行状态：现在到底能不能用（就绪 / 未就绪 + 原因），强调色只用在「需要注意」上。 */
function ReadyNote({ ready, reason, children }: { ready: boolean; reason: string; children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-xs leading-5 text-black/60">
      {ready ? null : <span aria-hidden="true" className="mt-1.5 h-2 w-2 shrink-0 bg-[#ff3366]" />}
      <span>
        {children}
        {ready ? null : <span className="text-[#ff3366]">（未就绪：{reason}）</span>}
      </span>
    </p>
  )
}

/** 写入失败时的一行提示：400 的 `message` 本身就是面向教师的一句话。 */
function SaveError({ message }: { message: string }) {
  if (!message) return null
  return <p className="text-xs leading-5 text-[#ff3366]">{message}</p>
}

/** 有改动才允许保存：草稿与服务端生效值逐项比对（没改就不让点，避免白跑一次写入）。 */
function isDirty(entries: { draft: string; server: string }[]): boolean {
  return entries.some((entry) => entry.draft !== entry.server)
}

function useSaveFeedback() {
  const save = useUpdateSettings()
  const { toast } = useToast()
  const submit = (patch: Parameters<typeof save.mutate>[0], title: string) =>
    save.mutate(patch, {
      onSuccess: () => toast({ title, description: '改动立即生效，不需要重启。', tone: 'default' }),
      onError: () => toast({ title: '设置未生效', description: '按提示修正后再保存。', tone: 'accent' }),
    })
  return { save, submit, error: save.isError ? settingsErrorMessage(save.error) : '' }
}

// ---- 供应商（多供应商并存，只加家不选模型）----

type InstanceView = SettingsViewBody['provider_instances'][number]

function ProviderListPanel({ view, catalog }: { view: SettingsViewBody; catalog: SettingsCatalogBody }) {
  const [addOpen, setAddOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<InstanceView | null>(null)
  const setDefault = useUpdateProviderInstance()
  const refresh = useRefreshProviderModels()
  const remove = useDeleteProviderInstance()
  const { toast } = useToast()
  const instances = view.provider_instances

  const dialectLabel = (instance: InstanceView) =>
    instance.provider === 'custom'
      ? '自定义 OpenAI 兼容服务'
      : (catalog.providers.find((provider) => provider.id === instance.provider)?.label ??
        instance.provider)

  const makeDefault = (instance: InstanceView) => {
    setDefault.mutate(
      { instanceId: instance.id, patch: { make_default: true } },
      {
        onSuccess: () =>
          toast({ title: '已设为默认供应商', description: instance.label, tone: 'default' }),
        onError: (failure) =>
          toast({
            title: '没设上',
            description: settingsErrorMessage(failure),
            tone: 'accent',
          }),
      },
    )
  }

  const refreshModels = (instance: InstanceView) => {
    refresh.mutate(instance.id, {
      onSuccess: (next) =>
        toast({
          title: '模型清单已刷新',
          description:
            next.models.length > 0 ? `${next.label}：${next.models.length} 个模型。` : next.models_error,
          tone: 'default',
        }),
      onError: (failure) =>
        toast({ title: '没刷新成', description: settingsErrorMessage(failure), tone: 'accent' }),
    })
  }

  const confirmDelete = () => {
    if (!deleteTarget) return
    remove.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast({
          title: '已删除供应商',
          description: `${deleteTarget.label}；使用它的任务已回落全局默认。`,
          tone: 'accent',
        })
        setDeleteTarget(null)
      },
      onError: (failure) =>
        toast({ title: '没删掉', description: settingsErrorMessage(failure), tone: 'accent' }),
    })
  }

  return (
    <Card>
      <CardHeader
        title="供应商"
        meta={instances.length > 0 ? `已添加 ${instances.length} 家` : '只加家，模型清单自动拉取'}
      />
      <CardBody className="flex flex-col gap-3">
        {instances.length === 0 ? (
          <p className="text-sm leading-6 text-black/60">
            还没有添加供应商：对话、生成、检索等云端能力都处于「未配置」，相关操作会给出指向本页的
            引导而不是假结果。添加一家并粘贴 Key 后，它的模型清单会自动拉取进统一模型池；第一家自动成为全局默认。
          </p>
        ) : (
          instances.map((instance) => (
            <div
              key={instance.id}
              className="flex flex-col gap-2 rounded-none border-2 border-black px-3 py-2"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex min-w-0 flex-wrap items-baseline gap-2">
                  <span className="text-sm font-bold">{instance.label}</span>
                  {instance.is_default ? <Badge tone="solid">默认</Badge> : null}
                  <span className="text-xs text-black/60">{dialectLabel(instance)}</span>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {instance.is_default ? null : (
                    <Button
                      size="sm"
                      disabled={setDefault.isPending}
                      onClick={() => makeDefault(instance)}
                    >
                      设为默认
                    </Button>
                  )}
                  <Button size="sm" onClick={() => refreshModels(instance)}>
                    刷新模型
                  </Button>
                  <Button size="sm" onClick={() => setDeleteTarget(instance)}>
                    删除
                  </Button>
                </div>
              </div>
              <p className="text-xs leading-5 text-black/60">
                {instance.base_url || '（无地址）'} · 模型 {instance.models.length} 个 · Key{' '}
                {instance.key_configured ? instance.key_masked : '未配置'}
              </p>
              {instance.models_error ? (
                <p className="text-xs leading-5 text-[#ff3366]">
                  模型清单没拉到：{instance.models_error}（可点刷新重试，或在下拉里手动填写模型）
                </p>
              ) : null}
              <ReadyNote ready={instance.ready} reason={instance.reason}>
                {instance.ready ? '已就绪：地址、Key 齐全，可被任务指派。' : '这一家还不能用：'}
              </ReadyNote>
            </div>
          ))
        )}
      </CardBody>
      <CardFooter>
        <Button variant="accent" onClick={() => setAddOpen(true)}>
          添加供应商
        </Button>
      </CardFooter>

      {addOpen ? (
        <AddProviderDialog
          catalog={catalog}
          onClose={() => setAddOpen(false)}
          onAdded={() => undefined}
        />
      ) : null}
      {deleteTarget ? (
        <Dialog
          open
          onOpenChange={(next) => {
            if (!next) setDeleteTarget(null)
          }}
          title="删除供应商"
          description={deleteTarget.label}
          size="sm"
          footer={
            <>
              <Button size="sm" onClick={() => setDeleteTarget(null)}>
                取消
              </Button>
              <Button
                variant="accent"
                size="sm"
                disabled={remove.isPending}
                onClick={confirmDelete}
              >
                {remove.isPending ? '正在删除…' : '删除'}
              </Button>
            </>
          }
        >
          <p className="text-sm leading-6">
            删除后这家不再可用；指到它的任务会回落全局默认（默认被删则回落剩余第一家）。
            Key 随这一条删除，{'.env'} 里的原值不受影响。
          </p>
        </Dialog>
      ) : null}
    </Card>
  )
}

// ---- 全局默认（从统一模型池选一个具体模型）----

function GlobalDefaultPanel({ view }: { view: SettingsViewBody }) {
  const drafts = useDrafts(view)
  const { save, submit, error } = useSaveFeedback()
  const pool = poolOf(view)
  const defaultInstanceId =
    view.provider_instances.find((instance) => instance.is_default)?.id ?? ''

  /** 当前全局默认模型：编码成选择器取值（实例::模型），不在池里的按手动填写处理。 */
  const currentModel = view.items.find((item) => item.name === 'llm_model')?.value ?? ''
  const composite = currentModel
    ? pool.some((entry) => entry.instanceId === defaultInstanceId && entry.model === currentModel)
      ? `${defaultInstanceId}::${currentModel}`
      : MANUAL_MODEL
    : defaultInstanceId
      ? FOLLOW_GLOBAL
      : ''

  const draft = drafts.valueOf('global-model', composite)
  const [manualInstance, setManualInstance] = useState(defaultInstanceId)
  const manualModelDraft = drafts.valueOf('global-manual-model', currentModel)

  const pickProviderOptions: PickerOption[] = view.provider_instances.map((instance) => ({
    id: instance.id,
    label: instance.label,
  }))

  const dirty = draft !== composite

  const saveGlobal = () => {
    if (draft === FOLLOW_GLOBAL) {
      // 全局默认不选具体模型：清除显式模型，调用时回落默认供应商的预设
      submit(settingsPatch({ llm_model: '' }), '全局默认已保存')
      return
    }
    const [instanceId, model] =
      draft === MANUAL_MODEL
        ? [manualInstance || defaultInstanceId, manualModelDraft]
        : draft.split('::')
    submit(
      settingsPatch({
        default_provider_instance: instanceId,
        llm_model: model,
      }),
      '全局默认已保存',
    )
  }

  const pickerOptions: PickerOption[] = [
    { id: FOLLOW_GLOBAL, label: '跟随默认供应商的预设模型' },
    ...pool.map(poolOption),
    { id: MANUAL_MODEL, label: '手动填写模型 ID…' },
  ]

  if (view.provider_instances.length === 0) {
    return (
      <Card>
        <CardHeader title="全局默认" meta="先添加供应商" />
        <CardBody>
          <p className="text-sm leading-6 text-black/60">
            全局默认 = 一个具体的「供应商 + 模型」；任务级没单独指派的都跟随它。先在上方添加
            至少一家供应商。
          </p>
        </CardBody>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader
        title="全局默认"
        meta={draft === FOLLOW_GLOBAL ? '未单独选模型：回落默认供应商的预设' : '一个具体模型'}
      />
      <CardBody className="flex flex-col gap-3">
        <Field
          htmlFor="settings-global-model"
          label="默认模型"
          hint="统一模型池：所有已添加供应商的模型合并在一起，每条标注来自哪家。"
        >
          <OptionPicker
            id="settings-global-model"
            aria-label="全局默认模型"
            menuLabel="全局默认模型"
            value={draft}
            onChange={(next) => drafts.setValue('global-model', next)}
            options={pickerOptions}
          />
        </Field>
        {draft === MANUAL_MODEL ? (
          <>
            <Field htmlFor="settings-global-manual-instance" label="用哪一家">
              <OptionPicker
                id="settings-global-manual-instance"
                aria-label="全局默认的供应商"
                menuLabel="供应商"
                value={manualInstance}
                onChange={setManualInstance}
                options={pickProviderOptions}
              />
            </Field>
            <Field htmlFor="settings-global-manual-model" label="模型 ID">
              <Input
                id="settings-global-manual-model"
                value={manualModelDraft}
                placeholder="例如 deepseek-chat"
                onChange={(event) => drafts.setValue('global-manual-model', event.target.value)}
              />
            </Field>
          </>
        ) : null}
        <SaveError message={error} />
      </CardBody>
      <CardFooter>
        <Button variant="accent" disabled={!dirty || save.isPending} onClick={saveGlobal}>
          保存全局默认
        </Button>
      </CardFooter>
    </Card>
  )
}

// ---- 任务级模型（每个任务从统一模型池选模型，默认跟随全局）----

function TaskModelPanel({ view }: { view: SettingsViewBody }) {
  const drafts = useDrafts(view)
  const { save, submit, error } = useSaveFeedback()
  const pool = poolOf(view)

  const pickProviderOptions: PickerOption[] = view.provider_instances.map((instance) => ({
    id: instance.id,
    label: instance.label,
  }))

  /** 任务当前取值 → 选择器取值。 */
  const currentValueOf = (task: SettingsViewBody['tasks'][number]): string => {
    if (task.selected_provider && task.selected) return `${task.selected_provider}::${task.selected}`
    if (task.selected_provider && !task.selected) return MANUAL_MODEL
    return FOLLOW_GLOBAL
  }

  const pickerValueOf = (task: SettingsViewBody['tasks'][number]) =>
    drafts.valueOf(`task-pick-${task.task}`, currentValueOf(task))
  const manualInstanceOf = (task: SettingsViewBody['tasks'][number]) =>
    drafts.valueOf(`task-manual-instance-${task.task}`, task.selected_provider || task.provider)
  const manualModelOf = (task: SettingsViewBody['tasks'][number]) =>
    drafts.valueOf(`task-manual-model-${task.task}`, task.selected)

  const dirtyEntries = view.tasks.map((task) => ({
    draft: pickerValueOf(task),
    server: currentValueOf(task),
  }))
  const dirty = isDirty(dirtyEntries)

  const saveTasks = () => {
    const patch: Record<string, string> = {}
    for (const task of view.tasks) {
      const pick = pickerValueOf(task)
      if (pick === FOLLOW_GLOBAL) {
        patch[task.provider_field] = ''
        patch[task.field] = ''
      } else if (pick === MANUAL_MODEL) {
        patch[task.provider_field] = manualInstanceOf(task)
        patch[task.field] = manualModelOf(task)
      } else {
        const [instanceId, model] = pick.split('::')
        patch[task.provider_field] = instanceId
        patch[task.field] = model
      }
    }
    submit(settingsPatch(patch), '任务级模型已生效')
  }

  if (view.provider_instances.length === 0) {
    return (
      <Card>
        <CardHeader title="任务级模型" meta="先添加供应商，再按任务指定" />
        <CardBody>
          <p className="text-sm leading-6 text-black/60">
            每个任务（意图分析 / 生成 / 冲突比对）可以从统一模型池里各选一个模型；没选的跟随
            全局默认。便宜的任务用便宜档位，生成要「写得好」。先在上方添加至少一家供应商。
          </p>
        </CardBody>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader title="任务级模型" meta="每个任务选一个模型，留空跟随全局默认" />
      <CardBody className="flex flex-col gap-4">
        {view.tasks.map((task) => {
          const pick = pickerValueOf(task)
          return (
            <div key={task.task} className="flex flex-col gap-2">
              <Field
                htmlFor={`settings-task-${task.task}`}
                label={task.label}
                hint={`实际用：${task.provider_label || '（未配置）'} · ${task.model || '—'}（${task.source}）`}
              >
                <OptionPicker
                  id={`settings-task-${task.task}`}
                  aria-label={`${task.label}的模型`}
                  menuLabel={`${task.label}的模型`}
                  value={pick}
                  onChange={(next) => drafts.setValue(`task-pick-${task.task}`, next)}
                  options={[
                    { id: FOLLOW_GLOBAL, label: '跟随全局默认' },
                    ...pool.map(poolOption),
                    { id: MANUAL_MODEL, label: '手动填写模型 ID…' },
                  ]}
                />
              </Field>
              {pick === MANUAL_MODEL ? (
                <>
                  <Field htmlFor={`settings-task-${task.task}-instance`} label="用哪一家">
                    <OptionPicker
                      id={`settings-task-${task.task}-instance`}
                      aria-label={`${task.label}的供应商`}
                      menuLabel="供应商"
                      value={manualInstanceOf(task)}
                      onChange={(next) => drafts.setValue(`task-manual-instance-${task.task}`, next)}
                      options={pickProviderOptions}
                    />
                  </Field>
                  <Field htmlFor={`settings-task-${task.task}-model`} label="模型 ID">
                    <Input
                      id={`settings-task-${task.task}-model`}
                      value={manualModelOf(task)}
                      placeholder="例如 deepseek-reasoner"
                      onChange={(event) =>
                        drafts.setValue(`task-manual-model-${task.task}`, event.target.value)
                      }
                    />
                  </Field>
                </>
              ) : null}
            </div>
          )
        })}
        <p className="text-xs leading-5 text-black/60">
          便宜的任务用便宜档位：意图分析与冲突比对多数时候只要「读懂」，生成要「写得好」。
        </p>
        <SaveError message={error} />
      </CardBody>
      <CardFooter>
        <Button variant="accent" disabled={!dirty || save.isPending} onClick={saveTasks}>
          保存模型档位
        </Button>
      </CardFooter>
    </Card>
  )
}

// ---- 能力实现 ----

/**
 * 哪一档实现需要哪个 Key：选到它就在下面显示对应的 Key 输入框。
 * 没选到的不显示——设置页一次只做一件事，不把七个 Key 堆在一起。
 */
const KEY_BY_IMPLEMENTATION: Record<string, Record<string, string>> = {
  asr_provider: { auto: 'asr_api_key', paraformer: 'asr_api_key' },
  pdf_strategy: { mineru: 'mineru_token', mineru_then_pypdf: 'mineru_token' },
  search_provider: { auto: 'bocha_api_key', bocha: 'bocha_api_key' },
  embedding_provider: { openai: 'embedding_api_key' },
}

function CapabilityPanel({ view, catalog }: { view: SettingsViewBody; catalog: SettingsCatalogBody }) {
  const drafts = useDrafts(view)
  const { save, submit, error } = useSaveFeedback()

  const itemValue = (name: string) => view.items.find((item) => item.name === name)?.value ?? ''
  const keyStateOf = (field: string) => view.keys.find((item) => item.field === field)

  const patch: Record<string, string> = {}
  for (const capability of catalog.capabilities) {
    const current = view.capabilities.find((item) => item.key === capability.key)?.value ?? ''
    patch[capability.key] = drafts.valueOf(capability.key, current)
  }
  patch.embedding_base_url = drafts.valueOf('embedding_base_url', itemValue('embedding_base_url'))
  patch.embedding_model = drafts.valueOf('embedding_model', itemValue('embedding_model'))
  // 只有教师真粘了 Key 才写 Key：没粘的项不写，避免把已配置的 Key 用空值抹掉
  for (const [capabilityKey, byImplementation] of Object.entries(KEY_BY_IMPLEMENTATION)) {
    const keyField = byImplementation[patch[capabilityKey] ?? '']
    const draft = keyField ? drafts.valueOf(keyField, '').trim() : ''
    if (keyField && draft) patch[keyField] = draft
  }

  const dirty =
    isDirty([
      ...catalog.capabilities.map((capability) => ({
        draft: patch[capability.key] ?? '',
        server: view.capabilities.find((item) => item.key === capability.key)?.value ?? '',
      })),
      { draft: patch.embedding_base_url ?? '', server: itemValue('embedding_base_url') },
      { draft: patch.embedding_model ?? '', server: itemValue('embedding_model') },
    ]) ||
    // 或者刚粘了一个这一档需要的 Key（没粘就不算改动）
    Object.entries(KEY_BY_IMPLEMENTATION).some(([capabilityKey, byImplementation]) => {
      const keyField = byImplementation[patch[capabilityKey] ?? '']
      return keyField ? drafts.valueOf(keyField, '').trim() !== '' : false
    })

  return (
    <Card>
      <CardHeader title="能力实现" meta="语音转写 / PDF 解析 / 网络搜索 / 向量化 / 检索 / 分块" />
      <CardBody className="flex flex-col gap-4">
        {catalog.capabilities.map((capability) => {
          const state = view.capabilities.find((item) => item.key === capability.key)
          const value = patch[capability.key] ?? ''
          const keyField = KEY_BY_IMPLEMENTATION[capability.key]?.[value]
          const keyState = keyField ? keyStateOf(keyField) : undefined
          return (
            <div key={capability.key} className="flex flex-col gap-2">
              <Field htmlFor={`settings-${capability.key}`} label={capability.label} hint={capability.note}>
                <OptionPicker
                  id={`settings-${capability.key}`}
                  aria-label={capability.label}
                  menuLabel={capability.label}
                  value={value}
                  onChange={(next) => drafts.setValue(capability.key, next)}
                  options={capability.options.map<PickerOption>((option) => ({
                    id: option.id,
                    label: option.label,
                  }))}
                />
              </Field>
              <ReadyNote ready={state?.ready ?? true} reason={state?.reason ?? ''}>
                当前：{state?.value_label}（{state?.source}）
              </ReadyNote>
              {keyField ? (
                <Field
                  htmlFor={`settings-${keyField}`}
                  label={keyState?.label ?? 'API Key'}
                  hint={
                    keyState?.configured
                      ? `已配置（回读只显示掩码 ${keyState.masked}）。`
                      : '这一档需要 Key 才能用；没有 Key 时该能力保持未配置，相关操作会提示到这里来配置。'
                  }
                >
                  <Input
                    id={`settings-${keyField}`}
                    type="password"
                    autoComplete="off"
                    placeholder={keyState?.masked || '粘贴 Key'}
                    value={drafts.valueOf(keyField, '')}
                    onChange={(event) => drafts.setValue(keyField, event.target.value)}
                  />
                </Field>
              ) : null}
              {capability.key === 'embedding_provider' && value === 'openai' ? (
                <>
                  <Field htmlFor="settings-embedding_base_url" label="向量化服务地址（base_url）">
                    <Input
                      id="settings-embedding_base_url"
                      placeholder="https://example.com/v1"
                      value={patch.embedding_base_url}
                      onChange={(event) => drafts.setValue('embedding_base_url', event.target.value)}
                    />
                  </Field>
                  <Field htmlFor="settings-embedding_model" label="向量化模型 ID">
                    <Input
                      id="settings-embedding_model"
                      placeholder="例如 bge-m3"
                      value={patch.embedding_model}
                      onChange={(event) => drafts.setValue('embedding_model', event.target.value)}
                    />
                  </Field>
                </>
              ) : null}
            </div>
          )
        })}
        <p className="text-xs leading-5 text-black/60">
          换向量化口径后，向量库里的向量与新的口径不一致，需要重建向量库再检索。
        </p>
        <SaveError message={error} />
      </CardBody>
      <CardFooter>
        <Button
          variant="accent"
          disabled={!dirty || save.isPending}
          onClick={() => submit(settingsPatch(patch), '能力实现已切换')}
        >
          保存能力实现
        </Button>
      </CardFooter>
    </Card>
  )
}
