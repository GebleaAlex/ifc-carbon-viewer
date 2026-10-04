<script setup lang="ts">
import { computed } from 'vue'
import { useViewerStore } from '../../stores/viewer'
import { storeyMaterialStacks, UNCLASSIFIED } from '../../lib/aggregate'
import { formatCarbon, UNCLASSIFIED_COLOR } from '../../lib/colors'

// Carbon per storey, each bar split by material: shows at a glance which floor is heavy and why.
const store = useViewerStore()
const stacks = computed(() => [...storeyMaterialStacks(store.elements, store.storeys)].reverse())
const max = computed(() => Math.max(...stacks.value.map((s) => s.total), 1))
const color = (category: string) =>
  category === UNCLASSIFIED ? UNCLASSIFIED_COLOR : (store.factorColors[category] ?? UNCLASSIFIED_COLOR)
const isActive = (storey: string) => store.focus?.kind === 'storey' && store.focus.key === storey
</script>

<template>
  <section v-if="stacks.length">
    <h3 class="section-title mb-2">By storey and material</h3>
    <ul class="space-y-1">
      <li v-for="stack in stacks" :key="stack.storey">
        <button
          class="grid w-full grid-cols-[72px_minmax(0,1fr)_56px] items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs transition hover:bg-ink-700/60"
          :class="isActive(stack.storey) ? 'bg-accent/10 ring-1 ring-accent/40' : ''"
          :title="`Show only ${stack.storey}`"
          @click="store.toggleFocus({ kind: 'storey', key: stack.storey, label: stack.storey })"
        >
          <span class="truncate text-ink-100">{{ stack.storey }}</span>
          <span class="flex h-3 overflow-hidden rounded-sm bg-ink-700" :style="{ width: `${(stack.total / max) * 100}%` }">
            <span
              v-for="segment in stack.segments"
              :key="segment.category"
              class="h-full"
              :style="{ width: `${(segment.carbon / stack.total) * 100}%`, background: color(segment.category) }"
              :title="`${store.factorLabels[segment.category] ?? segment.category}: ${formatCarbon(segment.carbon)}`"
            />
          </span>
          <span class="text-right font-mono text-ink-200">{{ formatCarbon(stack.total) }}</span>
        </button>
      </li>
    </ul>
  </section>
</template>
