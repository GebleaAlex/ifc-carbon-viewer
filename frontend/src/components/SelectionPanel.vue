<script setup lang="ts">
import { computed } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { UNCLASSIFIED_COLOR, formatCarbon, formatNumber } from '../lib/colors'

const store = useViewerStore()
const element = computed(() => store.selectedElement)
const detail = computed(() => store.selectedDetail)
const factor = computed(() => store.factors.find((f) => f.category === element.value?.material_category) ?? null)

function display(value: unknown): string {
  if (value === null || value === undefined) return '–'
  if (typeof value === 'number') return formatNumber(value, 3)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<template>
  <div v-if="!element" class="text-sm text-ink-300">
    Click an element in the 3D view, or pick one from the Elements tab, to see its properties and carbon estimate.
  </div>
  <div v-else class="space-y-4 text-sm">
    <header class="flex items-start gap-3">
      <span
        class="mt-1 h-3 w-3 shrink-0 rounded-sm"
        :style="{ background: store.factorColors[element.material_category ?? ''] ?? UNCLASSIFIED_COLOR }"
      />
      <div class="min-w-0 flex-1">
        <h2 class="truncate text-base font-semibold">{{ element.name ?? element.global_id }}</h2>
        <div class="mt-0.5 flex flex-wrap gap-1.5 text-[11px]">
          <span class="pill">{{ element.ifc_class }}</span>
          <span v-if="element.storey" class="pill">{{ element.storey }}</span>
          <span v-if="detail?.predefined_type" class="pill">{{ detail.predefined_type }}</span>
          <span v-if="element.type_name" class="pill">{{ element.type_name }}</span>
        </div>
      </div>
      <button class="text-ink-300 hover:text-ink-100" title="Clear selection" @click="store.select(null)">✕</button>
    </header>

    <div class="grid grid-cols-2 gap-2 text-xs">
      <div class="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
        <div class="text-ink-500">Embodied carbon</div>
        <div class="mt-0.5 font-mono text-lg text-good">{{ formatCarbon(element.carbon_kgco2e) }}</div>
      </div>
      <div class="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
        <div class="text-ink-500">Mass</div>
        <div class="mt-0.5 font-mono text-lg">{{ formatNumber(element.mass_kg, 0, 'kg') }}</div>
      </div>
      <div class="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
        <div class="flex items-center justify-between text-ink-500">
          <span>Volume</span>
          <span v-if="element.volume_source" class="pill py-0 text-[10px]">{{ element.volume_source }}</span>
        </div>
        <div class="mt-0.5 font-mono text-lg">{{ formatNumber(element.volume_m3, 3, 'm³') }}</div>
      </div>
      <div class="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
        <div class="text-ink-500">Material category</div>
        <div class="mt-0.5 text-lg">{{ factor?.label ?? 'Unclassified' }}</div>
      </div>
    </div>

    <section v-if="factor" class="rounded-lg border border-ink-700 p-3 text-xs">
      <div class="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-300">How this was estimated</div>
      <div class="font-mono text-ink-200">
        {{ formatNumber(element.volume_m3, 3) }} m³ × {{ factor.density_kg_m3 }} kg/m³ × {{ factor.factor_kgco2e_per_kg }} kgCO₂e/kg
      </div>
      <p v-if="factor.note" class="mt-1 text-ink-500">{{ factor.note }}</p>
    </section>

    <section class="text-xs">
      <div class="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Materials</div>
      <ul v-if="element.materials.length" class="flex flex-wrap gap-1.5">
        <li v-for="m in element.materials" :key="m" class="pill">{{ m }}</li>
      </ul>
      <div v-else class="text-ink-500">No material assigned in the model.</div>
    </section>

    <section class="text-xs">
      <div class="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Identity</div>
      <dl class="grid grid-cols-[110px_1fr] gap-y-1">
        <dt class="text-ink-500">GlobalId</dt>
        <dd class="break-all font-mono">{{ element.global_id }}</dd>
        <dt class="text-ink-500">Express id</dt>
        <dd class="font-mono">#{{ element.express_id }}</dd>
        <dt v-if="detail?.object_type" class="text-ink-500">Object type</dt>
        <dd v-if="detail?.object_type">{{ detail.object_type }}</dd>
        <dt v-if="detail?.description" class="text-ink-500">Description</dt>
        <dd v-if="detail?.description">{{ detail.description }}</dd>
      </dl>
    </section>

    <template v-if="detail">
      <details
        v-for="(props, name) in { ...detail.quantity_sets, ...detail.property_sets }"
        :key="name"
        class="rounded-lg border border-ink-700 text-xs"
        open
      >
        <summary class="cursor-pointer px-3 py-2 font-medium text-ink-100">{{ name }}</summary>
        <dl class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-3 gap-y-1 border-t border-ink-700/70 px-3 py-2">
          <template v-for="(value, key) in props" :key="key">
            <dt class="truncate text-ink-500" :title="String(key)">{{ key }}</dt>
            <dd class="break-words font-mono text-ink-200">{{ display(value) }}</dd>
          </template>
        </dl>
      </details>
    </template>
    <div v-else class="text-xs text-ink-500">Loading properties…</div>
  </div>
</template>
