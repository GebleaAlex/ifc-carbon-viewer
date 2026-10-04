export interface SelectOption<V> {
  value: V
  label: string
  sub?: string
  color?: string
  disabled?: boolean
}

export interface MenuItem {
  label: string
  sub?: string
  icon?: string
  danger?: boolean
  disabled?: boolean
  action: () => void
}
