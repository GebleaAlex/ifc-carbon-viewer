<script setup lang="ts">
import { computed } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { CARBON_RAMP, UNCLASSIFIED_COLOR, classColor, formatCarbon, storeyColor } from '../lib/colors'
import { categoriesOf, UNCLASSIFIED, type Focus } from '../lib/aggregate'

const store = useViewerStore()

interface Item {
  label: string
  color: string
  focus: Focus
}

const items = computed<Item[]>(() => {
  if (store.colorMode === 'class') {
    return store.ifcClasses.map((c) => ({ label: c, color: classColor(c), focus: { kind: 'class', key: c, label: c } }))
  }
  if (store.colorMode === 'storey') {
    return [...store.storeys]
      .reverse()
      .map((s) => ({ label: s, color: storeyColor(s, store.storeys), focus: { kind: 'storey', key: s, label: s } }))
  }
  if (store.colorMode === 'material') {
    const present = new Set(store.elements.filter((e) => !e.is_assembly).flatMap((e) => [e.material_category ?? UNCLASSIFIED]))
    const list: Item[] = store.factors
      .filter((f) => present.has(f.category))
      .map((f) => ({ label: f.label, color: f.color, focus: { kind: 'material', key: f.category, label: f.label } }))
    if (present.has(UNCLASSIFIED))
      list.push({ label: 'Unclassified', color: UNCLASSIFIED_COLOR, focus: { kind: 'material', key: UNCLASSIFIED, label: 'Unclassified' } })
    return list
  }
  return []
})

const isFocused = (item: Item) => store.focus?.kind === item.focus.kind && store.focus.key === item.focus.key
const gradient = `linear-gradient(90deg, ${CARBON_RAMP.join(', ')})`
// Material colours show the dominant material of each element; the legend says so to avoid confusion with layers.
const note = computed(() =>
  store.colorMode === 'material' && store.elements.some((e) => categoriesOf(e).length > 1)
    ? 'Layered elements show their main material'
    : null,
)
</script>

<template>
  <div v-if="store.currentId" class="panel max-w-[18rem] px-3 py-2 text-xs shadow-lg">
    <template v-if="store.colorMode === 'carbon'">
      <div class="mb-1 text-ink-300">Embodied carbon per element</div>
      <div class="h-2 w-56 rounded-full" :style="{ background: gradient }" />
      <div class="mt-1 flex justify-between font-mono text-[10px] text-ink-300">
        <span>0</span>
        <span>{{ formatCarbon(store.maxCarbon) }}</span>
      </div>
      <div class="mt-1 text-[10px] text-ink-500">square-root scale · grey = no estimate</div>
    </template>
    <template v-else>
      <ul class="grid max-h-40 grid-cols-2 gap-x-3 gap-y-0.5 overflow-auto">
        <li v-for="item in items" :key="item.label">
          <button
            class="flex w-full items-center gap-2 rounded px-1 py-0.5 text-left transition hover:bg-ink-700"
            :class="isFocused(item) ? 'bg-accent/15 text-accent' : 'text-ink-200'"
            :title="`Show only ${item.label}`"
            @click="store.toggleFocus(item.focus)"
          >
            <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: item.color }" />
            <span class="truncate">{{ item.label }}</span>
          </button>
        </li>
      </ul>
      <div v-if="note" class="mt-1 text-[10px] text-ink-500">{{ note }} · click to focus</div>
    </template>
  </div>
</template>
