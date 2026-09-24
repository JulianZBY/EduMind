import { MainPanel } from '../../components/layout/Workbench'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardFooter, CardHeader } from '../../components/ui/Card'
import { Field } from '../../components/ui/Field'
import { Input } from '../../components/ui/Input'

/**
 * 设置区：单页表单、编辑密度（大留白、单列窄容器）。
 * 票 04 只立形状：控件全部为只读骨架，读写接口接入（票 13）后开放。
 * 术语照 CONTEXT.md 第 8 节：供应商目录 / 任务级模型 / 掩码 / stub 模式。
 */
export function SettingsArea() {
  return (
    <MainPanel title="设置" tagline="云端能力与模型档位的配置页">
      <div className="mx-auto flex w-full max-w-xl flex-col gap-4 px-6 py-8">
        <Card>
          <CardHeader title="供应商目录" meta="选一家，粘贴 Key 即可用" />
          <CardBody className="flex flex-col gap-3">
            <Field
              htmlFor="settings-provider"
              label="供应商"
              hint="dashscope / deepseek / 硅基流动；目录之外的接入见最下面那张卡。"
            >
              <Input id="settings-provider" defaultValue="deepseek" disabled />
            </Field>
            <Field
              htmlFor="settings-api-key"
              label="API Key"
              hint="回读只显示尾部若干位：任何响应与表单都不回显明文。"
            >
              <Input id="settings-api-key" type="password" defaultValue="••••••••" disabled />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="任务级模型" meta="未设置的任务回落全局默认" />
          <CardBody className="flex flex-col gap-3">
            <Field htmlFor="settings-model-intent" label="意图分析" hint="便宜的任务用便宜档位。">
              <Input id="settings-model-intent" defaultValue="deepseek-chat" disabled />
            </Field>
            <Field htmlFor="settings-model-generate" label="生成">
              <Input id="settings-model-generate" defaultValue="deepseek-chat" disabled />
            </Field>
            <Field htmlFor="settings-model-conflict" label="冲突比对">
              <Input id="settings-model-conflict" defaultValue="deepseek-chat" disabled />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="能力实现" meta="语音转写 / PDF 解析 / 网络搜索" />
          <CardBody className="flex flex-col gap-3">
            <Field htmlFor="settings-asr" label="语音转写" hint="没有云端 Key 时回落 stub 模式，全链路仍可跑。">
              <Input id="settings-asr" defaultValue="stub" disabled />
            </Field>
            <Field htmlFor="settings-pdf" label="PDF 解析">
              <Input id="settings-pdf" defaultValue="mineru → pypdf 兜底" disabled />
            </Field>
            <Field htmlFor="settings-search" label="网络搜索">
              <Input id="settings-search" defaultValue="stub" disabled />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="自定义 OpenAI 兼容服务" meta="供应商目录之外" />
          <CardBody className="flex flex-col gap-3">
            <Field htmlFor="settings-base-url" label="base_url">
              <Input id="settings-base-url" placeholder="https://example.com/v1" disabled />
            </Field>
            <Field htmlFor="settings-model-id" label="模型 ID">
              <Input id="settings-model-id" placeholder="例如 my-model" disabled />
            </Field>
          </CardBody>
          <CardFooter>
            <Button disabled>测试连接</Button>
            <Button variant="accent" disabled>
              保存
            </Button>
          </CardFooter>
        </Card>

        <p className="text-xs leading-5 text-black/60">
          设置改动即时生效、不需要重启；当前页面为只读骨架，读写接口接入后开放。
        </p>
      </div>
    </MainPanel>
  )
}
