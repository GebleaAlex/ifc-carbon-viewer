<script setup lang="ts">
import { computed } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { CARBON_RAMP, UNCLASSIFIED_COLOR, classColor, formatCarbon } from '../lib/colors'

const store = useViewerStore()

const items = computed<{ label: string; color: string }[]>(() => {
  if (store.colorMode === 'class') {
    return store.ifcClasses.map((c) => ({ label: c, color: classColor(c) }))
  }
  if (store.colorMode === 'material') {
    const present = new Set(store.elements.map((e) => e.material_category ?? 'unclassified'))
    const list = store.factors.filter((f) => present.has(f.category)).map((f) => ({ label: f.label, color: f.color }))
    if (present.has('unclassified')) list.push({ label: 'Unclassified', color: UNCLASSIFIED_COLOR })
    return list
  }
  return []
})

const gradient = `linear-gradient(90deg, ${CARBON_RAMP.join(', ')})`
</script>

<template>
  <div v-if="store.currentId" class="panel max-w-xs px-3 py-2 text-xs">
    <template v-if="store.colorMode === 'carbon'">
      <div class="mb-1 flex items-center justify-between text-ink-300">
        <span>Embodied carbon per element</span>
      </div>
      <div class="h-2 w-56 rounded-full" :style="{ background: gradient }" />
      <div class="mt-1 flex justify-between font-mono text-[10px] text-ink-300">
        <span>0</span>
        <span>{{ formatCarbon(store.maxCarbon) }}</span>
      </div>
      <div class="mt-1 text-[10px] text-ink-500">square-root scale · grey = no estimate</div>
    </template>
    <ul v-else class="grid grid-cols-2 gap-x-4 gap-y-1">
      <li v-for="item in items" :key="item.label" class="flex items-center gap-2">
        <span class="h-2.5 w-2.5 rounded-sm" :style="{ background: item.color }" />
        <span class="truncate text-ink-200">{{ item.label }}</span>
      </li>
    </ul>
  </div>
</template>
