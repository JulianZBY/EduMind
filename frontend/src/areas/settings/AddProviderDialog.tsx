/**
 * 添加供应商（多供应商并存）：只选家 + 粘 Key，不选模型。
 *
 * 添加成功后后端同步拉取该家的 `/v1/models` 模型清单并缓存——设置页的「全局默认」与
 * 「任务级模型」都从统一模型池里选；拉取失败时可以在选择器里「手动填写」模型 ID。
 * 「自定义 OpenAI 兼容服务」也在这个入口里：填名称 + base_url 即可（模型 ID 同样
 * 由拉取或手动填写提供）。Key 只在提交时发给后端，界面不回显。
 */
import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'
import { useToast } from '../../components/ui/useToast'
import type { SettingsCatalogBody } from './queries'
import { settingsErrorMessage, useAddProviderInstance } from './queries'
import { OptionPicker } from './OptionPicker'

export interface AddProviderDialogProps {
  catalog: SettingsCatalogBody
  onClose: () => void
  /** 添加成功后的回调（默认第一家会自动成为全局默认，这里只做提示）。 */
  onAdded: (label: string, becameDefault: boolean) => void
}

export function AddProviderDialog({ catalog, onClose, onAdded }: AddProviderDialogProps) {
  const { toast } = useToast()
  const add = useAddProviderInstance()

  /** 可添加的目录家：后端目录里有什么就列什么（没有「演示兜底」这一类）。 */
  const choices = catalog.providers
  const [providerId, setProviderId] = useState(choices[0]?.id ?? '')
  const spec = catalog.providers.find((provider) => provider.id === providerId)
  const isCustom = providerId === 'custom'

  const [label, setLabel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    setError(null)
    add.mutate(
      {
        provider: providerId,
        label: label.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
      },
      {
        onSuccess: (instance) => {
          const modelNote =
            instance.models.length > 0
              ? `已拉取 ${instance.models.length} 个模型。`
              : instance.models_error
                ? '模型清单没拉到：稍后可刷新，或先手动填写模型。'
                : ''
          toast({
            title: instance.is_default ? '已添加供应商并设为默认' : '已添加供应商',
            description: `${instance.label}${modelNote ? `；${modelNote}` : ''}`,
            tone: 'default',
          })
          onAdded(instance.label, instance.is_default)
          onClose()
        },
        onError: (failure) => setError(settingsErrorMessage(failure)),
      },
    )
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="添加供应商"
      description="只选供应商 + 粘 Key；模型清单添加后自动拉取，选模型在「全局默认」与「任务级模型」里做。"
      size="md"
      footer={
        <>
          <Button size="sm" onClick={onClose}>
            取消
          </Button>
          <Button variant="accent" size="sm" disabled={add.isPending} onClick={submit}>
            {add.isPending ? '正在添加并拉取模型…' : '添加'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field htmlFor="add-provider-id" label="供应商" hint={spec?.note}>
          <OptionPicker
            id="add-provider-id"
            aria-label="供应商"
            menuLabel="供应商目录"
            value={providerId}
            onChange={setProviderId}
            options={choices.map((provider) => ({
              id: provider.id,
              label: provider.label,
              note: provider.base_url || provider.note,
            }))}
          />
        </Field>

        {isCustom ? (
          <>
            <Field htmlFor="add-provider-label" label="名称" hint="怎么叫顺手怎么填，比如「公司中转」。">
              <Input
                id="add-provider-label"
                value={label}
                placeholder="我的中转服务"
                onChange={(event) => setLabel(event.target.value)}
              />
            </Field>
            <Field
              htmlFor="add-provider-base-url"
              label="服务商地址（base_url）"
              hint="OpenAI 兼容的服务地址；模型 ID 在添加后再选或手动填。"
              error={error?.includes('base_url') ? error : undefined}
            >
              <Input
                id="add-provider-base-url"
                value={baseUrl}
                placeholder="https://example.com/v1"
                onChange={(event) => setBaseUrl(event.target.value)}
              />
            </Field>
          </>
        ) : null}

        <Field
          htmlFor="add-provider-key"
          label="API Key"
          hint="从服务商后台复制粘贴；Key 只在保存时提交，回读只显示掩码。"
          error={error && !error.includes('base_url') ? error : undefined}
        >
          <Input
            id="add-provider-key"
            type="password"
            autoComplete="off"
            value={apiKey}
            placeholder="粘贴 Key"
            onChange={(event) => setApiKey(event.target.value)}
          />
        </Field>
      </div>
    </Dialog>
  )
}
