<script setup lang="ts">
import { computed, ref } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { formatCarbon } from '../lib/colors'

const store = useViewerStore()
const query = ref('')
const sort = ref<'carbon' | 'name' | 'class'>('carbon')

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = store.elements.filter((e) => {
    if (!store.isVisible(e.global_id)) return false
    if (!q) return true
    return [e.name, e.ifc_class, e.storey, e.global_id, ...e.materials].some((v) => v?.toLowerCase().includes(q))
  })
  return [...list].sort((a, b) => {
    if (sort.value === 'carbon') return (b.carbon_kgco2e ?? -1) - (a.carbon_kgco2e ?? -1)
    if (sort.value === 'class') return a.ifc_class.localeCompare(b.ifc_class) || (a.name ?? '').localeCompare(b.name ?? '')
    return (a.name ?? '').localeCompare(b.name ?? '')
  })
})
</script>

<template>
  <div class="space-y-3">
    <div class="flex gap-2">
      <input
        v-model="query"
        type="search"
        placeholder="Search name, class, storey, material…"
        class="flex-1 rounded-lg border border-ink-600 bg-ink-900 px-3 py-1.5 text-sm outline-none placeholder:text-ink-500 focus:border-accent"
      />
      <select v-model="sort" class="rounded-lg border border-ink-600 bg-ink-900 px-2 text-xs outline-none">
        <option value="carbon">Carbon</option>
        <option value="name">Name</option>
        <option value="class">Class</option>
      </select>
    </div>
    <div class="text-[11px] text-ink-500">{{ filtered.length }} of {{ store.elements.length }} elements</div>
    <ul class="divide-y divide-ink-700/70 rounded-lg border border-ink-700">
      <li v-for="el in filtered" :key="el.global_id">
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
            <span class="block truncate text-ink-500">{{ el.ifc_class }}<template v-if="el.storey"> · {{ el.storey }}</template></span>
          </span>
          <span class="shrink-0 font-mono text-ink-200">{{ formatCarbon(el.carbon_kgco2e) }}</span>
        </button>
      </li>
    </ul>
  </div>
</template>
