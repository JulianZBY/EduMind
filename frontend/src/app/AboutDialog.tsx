import { Button } from '../components/ui/Button'
import { Dialog } from '../components/ui/Dialog'
import { useUiStore } from '../store/ui'

/** 关于弹层：应用定位 + 术语口径 + 接口事实源，给教师与协作者同一套说法。 */
export function AboutDialog() {
  const open = useUiStore((state) => state.aboutOpen)
  const setOpen = useUiStore((state) => state.setAboutOpen)

  return (
    <Dialog
      open={open}
      onOpenChange={setOpen}
      title="关于 EduMind"
      description="多模态 AI 备课智能体"
      size="md"
      footer={
        <Button variant="accent" onClick={() => setOpen(false)}>
          知道了
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <p>教师用多轮对话备课，融合本地教学资料与知识图谱，一键产出课件、教案、提纲、试卷与互动内容。</p>
        <ul className="flex flex-col gap-2">
          <li className="rounded-none border-2 border-black px-3 py-2">
            界面分六个区与设置：备课会话、知识库、生成物、知识图谱、冲突审核、题库。一区一件事。
          </li>
          <li className="rounded-none border-2 border-black px-3 py-2">
            生成物 = 课件、教案、提纲、试卷、互动内容的统称；勾选进本次备课的资料叫<b>参考资料</b>。
          </li>
          <li className="rounded-none border-2 border-black px-3 py-2">
            接口以 OpenAPI 为唯一事实源：前端类型由后端 schema 生成，不手抄。
          </li>
        </ul>
      </div>
    </Dialog>
  )
}
