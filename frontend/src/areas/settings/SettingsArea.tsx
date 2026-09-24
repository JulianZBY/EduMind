import { useState } from 'react'
import type { ReactNode } from 'react'

import { MainPanel } from '../../components/layout/Workbench'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardFooter, CardHeader } from '../../components/ui/Card'
import { Field } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'
import { useToast } from '../../components/ui/useToast'
import { OptionPicker } from './OptionPicker'
import type { PickerOption } from './OptionPicker'
import {
  settingsErrorMessage,
  settingsPatch,
  useSettingsCatalogQuery,
  useSettingsQuery,
  useUpdateSettings,
} from './queries'
import type { SettingsCatalogBody, SettingsViewBody } from './queries'

/**
 * 设置区：单页表单、编辑密度（一次只做一件事）。
 *
 * 四张卡各管一段：供应商目录 / 任务级模型 / 能力实现 / 自定义 OpenAI 兼容服务。
 * 每张卡只写自己那几个设置项，写入后服务端返回的就是新的生效配置，界面随之刷新——
 * 「改动即时生效、不需要重启」在界面上表现为没有「重启生效」这类提示。
 * Key 只有掩码会出现在响应里，输入框里的明文只来自教师自己粘贴。
 */
export function SettingsArea() {
  const settings = useSettingsQuery()
  const catalog = useSettingsCatalogQuery()

  if (settings.isPending || catalog.isPending) {
    // 加载态也先把第一张卡的标题立起来：页面结构立刻可见，不是一片空白。
    return (
      <MainPanel title="设置" tagline="云端能力与模型档位的配置页">
        <div className="mx-auto flex w-full max-w-xl flex-col gap-4 px-6 py-8">
          <Card>
            <CardHeader title="供应商目录" meta="选一家，粘贴 Key 即可用" />
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
        <ProviderPanel view={settings.data} catalog={catalog.data} />
        <TaskModelPanel view={settings.data} catalog={catalog.data} />
        <CapabilityPanel view={settings.data} catalog={catalog.data} />
        <CustomServicePanel view={settings.data} />
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

// ---- 供应商目录 ----

function ProviderPanel({ view, catalog }: { view: SettingsViewBody; catalog: SettingsCatalogBody }) {
  const drafts = useDrafts(view)
  const { save, submit, error } = useSaveFeedback()

  const provider = drafts.valueOf('llm_provider', view.provider.value)
  const selected = catalog.providers.find((item) => item.id === provider)
  const keyField = selected?.key_field ?? ''
  const keyState = view.keys.find((item) => item.field === keyField)
  const keyDraft = keyField ? drafts.valueOf(keyField, '') : ''
  const dirty =
    provider !== view.provider.value || (keyDraft.trim() !== '' && keyField !== '')

  return (
    <Card>
      <CardHeader title="供应商目录" meta="选一家，粘贴 Key 即可用" />
      <CardBody className="flex flex-col gap-3">
        <Field htmlFor="settings-provider" label="供应商" hint={selected?.note}>
          <OptionPicker
            id="settings-provider"
            aria-label="供应商"
            value={provider}
            onChange={(id) => drafts.setValue('llm_provider', id)}
            options={catalog.providers.map<PickerOption>((item) => ({
              id: item.id,
              label: item.label,
              note: item.base_url || (item.accepts_any_model ? '自行填地址与模型 ID' : undefined),
            }))}
          />
        </Field>
        {keyField ? (
          <Field
            htmlFor={`settings-${keyField}`}
            label={keyState?.label ?? 'API Key'}
            hint={
              keyState?.configured
                ? `已配置（回读只显示掩码 ${keyState.masked}）；要换 Key 直接粘贴新的。`
                : '从服务商后台复制 Key 粘贴到这里；没有 Key 也能跑（stub 模式）。'
            }
          >
            <Input
              id={`settings-${keyField}`}
              type="password"
              autoComplete="off"
              placeholder={keyState?.masked || '粘贴 Key'}
              value={keyDraft}
              onChange={(event) => drafts.setValue(keyField, event.target.value)}
            />
          </Field>
        ) : (
          <p className="text-xs leading-5 text-black/60">
            stub 模式不需要 Key：没有任何云端 Key 时全链路可跑，结果用于试用与联调。
          </p>
        )}
        <ReadyNote ready={view.provider.ready} reason={view.provider.reason}>
          当前生效：{view.provider.label}（{view.provider.source}）
        </ReadyNote>
        <SaveError message={error} />
      </CardBody>
      <CardFooter>
        {keyField && keyState?.configured ? (
          <Button
            disabled={save.isPending}
            onClick={() => submit(settingsPatch({ [keyField]: '' }), 'Key 已清除')}
          >
            清除 Key
          </Button>
        ) : null}
        <Button
          variant="accent"
          disabled={!dirty || save.isPending}
          onClick={() =>
            submit(
              settingsPatch({
                llm_provider: provider,
                [keyField]: keyField && keyDraft.trim() ? keyDraft : undefined,
              }),
              '供应商已切换',
            )
          }
        >
          保存供应商
        </Button>
      </CardFooter>
    </Card>
  )
}

// ---- 任务级模型 ----

function TaskModelPanel({ view, catalog }: { view: SettingsViewBody; catalog: SettingsCatalogBody }) {
  const drafts = useDrafts(view)
  const { save, submit, error } = useSaveFeedback()

  const provider = catalog.providers.find((item) => item.id === view.provider.value)
  const preset = provider?.chat_models[0] ?? ''
  const freeText = provider?.accepts_any_model ?? false
  const globalItem = view.items.find((item) => item.name === 'llm_model')
  const globalModel = drafts.valueOf('llm_model', globalItem?.value ?? '')

  const modelOptions = (emptyLabel: string): PickerOption[] => [
    { id: '', label: emptyLabel },
    ...(provider?.chat_models ?? []).map<PickerOption>((model) => ({ id: model, label: model })),
  ]

  const renderModelField = (id: string, label: string, value: string, fallback: string, emptyLabel: string) =>
    freeText ? (
      <Input
        id={id}
        autoComplete="off"
        placeholder="模型 ID"
        value={value}
        onChange={(event) => drafts.setValue(fallback, event.target.value)}
      />
    ) : (
      <OptionPicker
        id={id}
        aria-label={label}
        menuLabel={label}
        value={value}
        onChange={(next) => drafts.setValue(fallback, next)}
        options={modelOptions(emptyLabel)}
      />
    )

  const selectedOf = (field: string) => view.tasks.find((task) => task.field === field)?.selected ?? ''
  const patch = settingsPatch({
    llm_model: globalModel,
    task_model_intent: drafts.valueOf('task_model_intent', selectedOf('task_model_intent')),
    task_model_generate: drafts.valueOf('task_model_generate', selectedOf('task_model_generate')),
    task_model_conflict: drafts.valueOf('task_model_conflict', selectedOf('task_model_conflict')),
  })

  const dirty = isDirty([
    { draft: globalModel, server: globalItem?.value ?? '' },
    ...view.tasks.map((task) => ({ draft: drafts.valueOf(task.field, task.selected), server: task.selected })),
  ])

  return (
    <Card>
      <CardHeader title="任务级模型" meta="按任务选档位，未设置的任务回落全局默认" />
      <CardBody className="flex flex-col gap-3">
        <Field
          htmlFor="settings-llm_model"
          label="全局默认"
          hint={`实际用：${globalItem?.effective || '—'}（${globalItem?.source ?? ''}）`}
        >
          {renderModelField(
            'settings-llm_model',
            '全局默认模型',
            globalModel,
            'llm_model',
            preset ? `未设置（用预设 ${preset}）` : '未设置',
          )}
        </Field>
        {view.tasks.map((task) => (
          <Field
            key={task.field}
            htmlFor={`settings-${task.field}`}
            label={task.label}
            hint={`实际用：${task.model || '尚未确定'}（${task.source}）`}
          >
            {renderModelField(
              `settings-${task.field}`,
              task.label,
              drafts.valueOf(task.field, task.selected),
              task.field,
              '未设置（回落全局默认）',
            )}
          </Field>
        ))}
        <p className="text-xs leading-5 text-black/60">
          便宜的任务用便宜档位：意图分析与冲突比对多数时候只要「读懂」，生成要「写得好」。
        </p>
        <SaveError message={error} />
      </CardBody>
      <CardFooter>
        <Button
          variant="accent"
          disabled={!dirty || save.isPending}
          onClick={() => submit(patch, '任务级模型已生效')}
        >
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
  asr_provider: { paraformer: 'dashscope_api_key' },
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
                      : '这一档需要 Key 才能用；没有 Key 时请选 stub 模式。'
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

// ---- 自定义 OpenAI 兼容服务 ----

function CustomServicePanel({ view }: { view: SettingsViewBody }) {
  const drafts = useDrafts(view)
  const { save, submit, error } = useSaveFeedback()

  const itemValue = (name: string) => view.items.find((item) => item.name === name)?.value ?? ''
  const keyState = view.keys.find((item) => item.field === 'llm_api_key')
  const baseUrl = drafts.valueOf('llm_base_url', itemValue('llm_base_url'))
  const model = drafts.valueOf('llm_model', itemValue('llm_model'))
  const keyDraft = drafts.valueOf('llm_api_key', '')

  const dirty =
    isDirty([
      { draft: baseUrl, server: itemValue('llm_base_url') },
      { draft: model, server: itemValue('llm_model') },
    ]) || keyDraft.trim() !== ''

  return (
    <Card>
      <CardHeader title="自定义 OpenAI 兼容服务" meta="供应商目录之外" />
      <CardBody className="flex flex-col gap-3">
        <p className="text-xs leading-5 text-black/60">
          目录里没有的服务商走这里：填 base_url + 模型 ID + Key 即可用，模型 ID 不受目录限制。
          保存后供应商会切到「自定义 OpenAI 兼容服务」。
        </p>
        <Field
          htmlFor="settings-llm_base_url"
          label="服务商地址（base_url）"
          hint={`当前生效：${itemValue('llm_base_url') || view.provider.value}（留空即用供应商预设/不生效）`}
        >
          <Input
            id="settings-llm_base_url"
            placeholder="https://example.com/v1"
            value={baseUrl}
            onChange={(event) => drafts.setValue('llm_base_url', event.target.value)}
          />
        </Field>
        <Field htmlFor="settings-llm_model" label="模型 ID" hint="写在服务商文档里的模型名，原样填。">
          <Input
            id="settings-llm_model"
            placeholder="例如 my-model"
            value={model}
            onChange={(event) => drafts.setValue('llm_model', event.target.value)}
          />
        </Field>
        <Field
          htmlFor="settings-llm_api_key"
          label={keyState?.label ?? 'API Key'}
          hint={
            keyState?.configured
              ? `已配置（回读只显示掩码 ${keyState.masked}）。`
              : '自定义服务没有 stub 兜底，必须填 Key 才能用。'
          }
        >
          <Input
            id="settings-llm_api_key"
            type="password"
            autoComplete="off"
            placeholder={keyState?.masked || '粘贴 Key'}
            value={keyDraft}
            onChange={(event) => drafts.setValue('llm_api_key', event.target.value)}
          />
        </Field>
        {view.provider.value === 'custom' ? (
          <ReadyNote ready={view.provider.ready} reason={view.provider.reason}>
            当前生效：自定义 OpenAI 兼容服务
          </ReadyNote>
        ) : null}
        <SaveError message={error} />
      </CardBody>
      <CardFooter>
        <Button
          variant="accent"
          disabled={!dirty || save.isPending}
          onClick={() =>
            submit(
              settingsPatch({
                llm_provider: 'custom',
                llm_base_url: baseUrl,
                llm_model: model,
                llm_api_key: keyDraft.trim() ? keyDraft : undefined,
              }),
              '自定义服务已生效',
            )
          }
        >
          保存并启用
        </Button>
      </CardFooter>
    </Card>
  )
}
