import { SettingsArea } from './SettingsArea'
import type { AreaModule } from '../types'

/** 设置区注册：单页表单（编辑密度），不是业务区。 */
export const settingsArea: AreaModule = {
  id: 'settings',
  label: '设置',
  path: '/settings',
  order: 70,
  tagline: '云端能力与模型档位的配置页',
  routes: [
    {
      id: 'settings',
      path: 'settings',
      element: <SettingsArea />,
    },
  ],
}

export default settingsArea
