<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { formatCarbon } from '../lib/colors'
import { matchesFocus } from '../lib/aggregate'
import type { SelectOption } from './ui/types'
import UiSelect from './ui/UiSelect.vue'
import Icon from './ui/Icon.vue'

const PAGE = 200

const store = useViewerStore()
const query = ref('')
const sort = ref<'carbon' | 'name' | 'class' | 'storey'>('carbon')
const limit = ref(PAGE)

const sortOptions: SelectOption<'carbon' | 'name' | 'class' | 'storey'>[] = [
  { value: 'carbon', label: 'Carbon' },
  { value: 'name', label: 'Name' },
  { value: 'class', label: 'IFC class' },
  { value: 'storey', label: 'Storey' },
]

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const storeyIndex = new Map(store.storeys.map((s, i) => [s, i]))
  const list = store.elements.filter((e) => {
    if (!store.isVisible(e.global_id) || !matchesFocus(e, store.focus)) return false
    if (!q) return true
    return [e.name, e.ifc_class, e.storey, e.global_id, e.type_name, ...e.materials].some((v) =>
      v?.toLowerCase().includes(q),
    )
  })
  return [...list].sort((a, b) => {
    if (sort.value === 'carbon') return (b.carbon_kgco2e ?? -1) - (a.carbon_kgco2e ?? -1)
    if (sort.value === 'class') return a.ifc_class.localeCompare(b.ifc_class) || (a.name ?? '').localeCompare(b.name ?? '')
    if (sort.value === 'storey')
      return (storeyIndex.get(a.storey ?? '') ?? -1) - (storeyIndex.get(b.storey ?? '') ?? -1)
    return (a.name ?? '').localeCompare(b.name ?? '', undefined, { numeric: true })
  })
})
const shown = computed(() => filtered.value.slice(0, limit.value))
watch([query, sort, () => store.focus], () => (limit.value = PAGE))
</script>

<template>
  <div class="space-y-3">
    <div class="flex gap-2">
      <div class="flex flex-1 items-center gap-2 rounded-lg border border-ink-600 bg-ink-900 px-2.5 focus-within:border-accent">
        <Icon name="search" :size="14" class="text-ink-300" />
        <input
          v-model="query"
          type="search"
          placeholder="Name, class, storey, material…"
          class="h-8 w-full bg-transparent text-sm outline-none placeholder:text-ink-500"
        />
      </div>
      <div class="w-28 shrink-0">
        <UiSelect v-model="sort" :options="sortOptions" label="Sort by" :min-width="140" />
      </div>
    </div>
    <div class="flex items-center justify-between text-[11px] text-ink-500">
      <span>{{ filtered.length }} of {{ store.elements.length }} elements</span>
      <button v-if="store.focus" class="flex items-center gap-1 text-accent hover:underline" @click="store.focus = null">
        {{ store.focus.label }} <Icon name="close" :size="12" />
      </button>
    </div>
    <ul class="divide-y divide-ink-700/70 rounded-lg border border-ink-700">
      <li v-for="el in shown" :key="el.global_id">
        <button
          class="flex w-full items-center gap-3 px-3 py-2 text-left text-xs transition hover:bg-ink-700/60"
          :class="store.selectedId === el.global_id ? 'bg-ink-700/80' : ''"
          @click="store.select(el.global_id)"
          @mouseenter="store.hoveredId = el.global_id"
          @mouseleave="store.hoveredId = null"
        >
          <span class="h-2 w-2 shrink-0 rounded-sm" :style="{ background: store.colorFor(el.global_id) ?? '#64748b' }" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-ink-100">{{ el.name ?? el.global_id }}</span>
            <span class="block truncate text-ink-500">
              {{ el.ifc_class }}<template v-if="el.storey"> · {{ el.storey }}</template>
              <template v-if="el.is_assembly"> · assembly</template>
              <template v-else-if="el.layers.length > 1"> · {{ el.layers.length }} layers</template>
            </span>
          </span>
          <Icon v-if="!el.is_assembly && !el.material_category" name="warning" :size="13" class="shrink-0 text-warn" />
          <span class="shrink-0 font-mono text-ink-200">{{ el.is_assembly ? 'parts' : formatCarbon(el.carbon_kgco2e) }}</span>
        </button>
      </li>
      <li v-if="!filtered.length" class="px-3 py-6 text-center text-xs text-ink-300">No elements match.</li>
    </ul>
    <button
      v-if="filtered.length > shown.length"
      class="btn w-full justify-center text-xs"
      @click="limit += PAGE"
    >
      Show {{ Math.min(PAGE, filtered.length - shown.length) }} more
    </button>
  </div>
</template>
