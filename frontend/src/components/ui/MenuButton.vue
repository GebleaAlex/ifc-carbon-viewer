<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import Icon from './Icon.vue'
import type { MenuItem } from './types'

// A button that opens a short list of actions (Export, More). Items are plain objects so callers stay declarative.

const props = defineProps<{ label: string; icon?: string; items: MenuItem[]; iconOnly?: boolean }>()
const open = ref(false)
const root = ref<HTMLDivElement | null>(null)

function run(item: MenuItem) {
  if (item.disabled) return
  open.value = false
  item.action()
}

function onOutside(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) open.value = false
}

watch(open, (isOpen) => {
  if (isOpen) window.addEventListener('pointerdown', onOutside, true)
  else window.removeEventListener('pointerdown', onOutside, true)
})
onBeforeUnmount(() => window.removeEventListener('pointerdown', onOutside, true))
</script>

<template>
  <div ref="root" class="relative" @keydown.esc="open = false">
    <button
      class="btn"
      :class="{ 'icon-btn': props.iconOnly }"
      :aria-label="props.label"
      :title="props.label"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <Icon v-if="props.icon" :name="props.icon" />
      <span v-if="!props.iconOnly">{{ props.label }}</span>
      <Icon v-if="!props.iconOnly" name="chevron" :size="14" class="text-ink-300" />
    </button>
    <Transition name="pop">
      <div v-if="open" class="ui-select-menu absolute right-0 top-full mt-1.5 w-64 p-1" role="menu">
        <button
          v-for="item in props.items"
          :key="item.label"
          role="menuitem"
          class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition hover:bg-ink-700 disabled:cursor-not-allowed disabled:opacity-45"
          :class="item.danger ? 'text-bad' : 'text-ink-100'"
          :disabled="item.disabled"
          @click="run(item)"
        >
          <Icon v-if="item.icon" :name="item.icon" :class="item.danger ? 'text-bad' : 'text-ink-300'" />
          <span class="min-w-0 flex-1">
            <span class="block">{{ item.label }}</span>
            <span v-if="item.sub" class="block text-[11px] text-ink-300">{{ item.sub }}</span>
          </span>
        </button>
      </div>
    </Transition>
  </div>
</template>
