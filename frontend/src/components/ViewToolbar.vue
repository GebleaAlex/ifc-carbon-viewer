<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useViewerStore } from '../stores/viewer'
import type { ColorMode } from '../lib/colors'
import Icon from './ui/Icon.vue'

const store = useViewerStore()
const openPopover = ref<'storeys' | 'classes' | null>(null)
const root = ref<HTMLDivElement | null>(null)

const modes: { value: ColorMode; label: string; hint: string; key: string }[] = [
  { value: 'material', label: 'Material', hint: 'Colour by classified material', key: '1' },
  { value: 'carbon', label: 'Carbon', hint: 'Colour by embodied carbon', key: '2' },
  { value: 'class', label: 'IFC class', hint: 'Colour by IFC entity type', key: '3' },
  { value: 'storey', label: 'Storey', hint: 'Colour by storey', key: '4' },
]

function toggle(name: 'storeys' | 'classes') {
  openPopover.value = openPopover.value === name ? null : name
}

function onOutside(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) openPopover.value = null
}
watch(openPopover, (value) => {
  if (value) window.addEventListener('pointerdown', onOutside, true)
  else window.removeEventListener('pointerdown', onOutside, true)
})
onBeforeUnmount(() => window.removeEventListener('pointerdown', onOutside, true))
</script>

<template>
  <div ref="root" class="flex flex-wrap items-start gap-2">
    <div class="seg shadow-lg" role="group" aria-label="Colour mode">
      <button
        v-for="mode in modes"
        :key="mode.value"
        :aria-pressed="store.colorMode === mode.value"
        :title="`${mode.hint} (${mode.key})`"
        @click="store.colorMode = mode.value"
      >
        {{ mode.label }}
      </button>
    </div>

    <div v-if="store.storeys.length" class="relative">
      <button class="btn h-8 py-0 text-xs shadow-lg" :aria-expanded="openPopover === 'storeys'" @click="toggle('storeys')">
        <Icon name="storey" :size="14" /> Storeys
        <span v-if="store.hiddenStoreys.size" class="rounded bg-warn/20 px-1 text-warn">{{ store.hiddenStoreys.size }} hidden</span>
      </button>
      <Transition name="pop">
        <div v-if="openPopover === 'storeys'" class="ui-select-menu absolute left-0 top-full mt-1.5 w-64 p-1 text-xs">
          <div
            v-for="storey in [...store.storeys].reverse()"
            :key="storey"
            class="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-ink-700"
          >
            <button
              class="flex min-w-0 flex-1 items-center gap-2 text-left"
              :class="store.hiddenStoreys.has(storey) ? 'text-ink-500' : 'text-ink-100'"
              :title="store.hiddenStoreys.has(storey) ? 'Show' : 'Hide'"
              @click="store.toggleStorey(storey)"
            >
              <Icon :name="store.hiddenStoreys.has(storey) ? 'eyeOff' : 'eye'" :size="14" />
              <span class="truncate">{{ storey }}</span>
            </button>
            <button class="rounded px-1.5 py-0.5 text-ink-300 opacity-0 transition hover:bg-ink-600 hover:text-ink-100 group-hover:opacity-100" @click="store.soloStorey(storey)">
              only
            </button>
          </div>
        </div>
      </Transition>
    </div>

    <div v-if="store.ifcClasses.length" class="relative">
      <button class="btn h-8 py-0 text-xs shadow-lg" :aria-expanded="openPopover === 'classes'" @click="toggle('classes')">
        <Icon name="layers" :size="14" /> Classes
        <span v-if="store.hiddenClasses.size" class="rounded bg-warn/20 px-1 text-warn">{{ store.hiddenClasses.size }} hidden</span>
      </button>
      <Transition name="pop">
        <div v-if="openPopover === 'classes'" class="ui-select-menu absolute left-0 top-full mt-1.5 max-h-80 w-64 overflow-auto p-1 text-xs">
          <button
            v-for="ifcClass in store.ifcClasses"
            :key="ifcClass"
            class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-ink-700"
            :class="store.hiddenClasses.has(ifcClass) ? 'text-ink-500' : 'text-ink-100'"
            @click="store.toggleClass(ifcClass)"
          >
            <Icon :name="store.hiddenClasses.has(ifcClass) ? 'eyeOff' : 'eye'" :size="14" />
            <span class="flex-1 truncate">{{ ifcClass }}</span>
            <span class="text-ink-300">{{ store.currentModel?.ifc_classes[ifcClass] }}</span>
          </button>
        </div>
      </Transition>
    </div>
  </div>
</template>
