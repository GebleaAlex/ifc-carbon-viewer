import { shallowRef } from 'vue'

/** A themed replacement for window.confirm(): `if (await confirmDialog({...}))`. */
export interface ConfirmOptions {
  title: string
  message: string
  confirm?: string
  danger?: boolean
}

interface ConfirmState extends Required<ConfirmOptions> {
  resolve: (ok: boolean) => void
}

export const confirmState = shallowRef<ConfirmState | null>(null)

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  confirmState.value?.resolve(false)
  return new Promise((resolve) => {
    confirmState.value = { confirm: 'Confirm', danger: false, ...options, resolve }
  })
}

export function resolveConfirm(ok: boolean): void {
  const state = confirmState.value
  confirmState.value = null
  state?.resolve(ok)
}
