/**
 * 线性图标：线宽统一 2，只用 currentColor（黑白随文，不做彩色图标、不做填充图标）。
 */
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function Icon({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  )
}

export function CloseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.5 3.5 12.5 12.5M12.5 3.5 3.5 12.5" />
    </Icon>
  )
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 6.5 8 10.5 12 6.5" />
    </Icon>
  )
}

/** 折叠区级导航：直角方框加一条内竖线，不做斜向箭头。 */
export function RailToggleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="2.5" y="3.5" width="11" height="9" />
      <path d="M6.5 3.5V12.5" />
    </Icon>
  )
}

export function InfoIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 7V11.5M8 4.5V5.5" />
    </Icon>
  )
}

export function PulseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M1.5 8H5L6.5 4.5 9.5 11.5 11 8H14.5" />
    </Icon>
  )
}

/** 状态点：直角方框，用色走强调色（成功/失败都不引入红绿蓝）。 */
export function MarkerIcon(props: IconProps) {
  return (
    <Icon fill="currentColor" stroke="none" {...props}>
      <rect x="3" y="3" width="10" height="10" />
    </Icon>
  )
}
