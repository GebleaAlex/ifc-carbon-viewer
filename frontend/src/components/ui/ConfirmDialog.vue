<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { confirmState, resolveConfirm } from '../../lib/confirm'

const confirmButton = ref<HTMLButtonElement | null>(null)
watch(
  () => confirmState.value,
  async (state) => {
    if (!state) return
    await nextTick()
    confirmButton.value?.focus()
  },
)
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="confirmState"
        class="fixed inset-0 z-[60] flex items-center justify-center bg-ink-950/70 p-4 backdrop-blur-sm"
        @click.self="resolveConfirm(false)"
        @keydown.esc="resolveConfirm(false)"
      >
        <div class="panel w-full max-w-sm p-5 shadow-2xl" role="alertdialog" aria-modal="true" :aria-label="confirmState.title">
          <h2 class="text-base font-semibold">{{ confirmState.title }}</h2>
          <p class="mt-1.5 text-sm text-ink-300">{{ confirmState.message }}</p>
          <div class="mt-5 flex justify-end gap-2">
            <button class="btn" @click="resolveConfirm(false)">Cancel</button>
            <button
              ref="confirmButton"
              class="btn"
              :class="confirmState.danger ? 'btn-danger' : 'btn-primary'"
              @click="resolveConfirm(true)"
            >
              {{ confirmState.confirm }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
