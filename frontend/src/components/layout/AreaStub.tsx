import { useParams } from 'react-router'
import { EmptyState } from '../ui/EmptyState'

export interface AreaStubProps {
  title: string
  description: string
  /** 传了 paramKey 就是「选中对象」占位：把 URL 里的对象 id 直接显示出来（URL 即路由的证据）。 */
  paramKey?: string
  objectLabel?: string
}

/**
 * 票 04 的各区空壳：只保证「可导航、风格到位、密度正确」。
 * 真正的业务功能由后续票（06/08/09/10/11/12/13）在各区目录里替换本组件。
 */
export function AreaStub({ title, description, paramKey, objectLabel }: AreaStubProps) {
  const params = useParams()
  const selected = paramKey ? params[paramKey] : undefined

  return (
    <EmptyState
      title={title}
      description={description}
      meta={selected ? `${objectLabel ?? '选中对象'}：${selected}` : undefined}
    />
  )
}
