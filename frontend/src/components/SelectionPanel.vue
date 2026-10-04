<script setup lang="ts">
import { computed } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { UNCLASSIFIED_COLOR, formatCarbon, formatNumber, formatPercent } from '../lib/colors'
import { viewerBridge } from '../lib/viewerBridge'
import Icon from './ui/Icon.vue'

const store = useViewerStore()
const element = computed(() => store.selectedElement)
const detail = computed(() => store.selectedDetail)
const factorFor = (category: string | null) => store.factors.find((f) => f.category === category) ?? null
const colorOf = (category: string | null) => (category ? (store.factorColors[category] ?? UNCLASSIFIED_COLOR) : UNCLASSIFIED_COLOR)

const layers = computed(() => element.value?.layers ?? [])
const layerTotal = computed(() => layers.value.reduce((sum, l) => sum + (l.volume_m3 ?? 0), 0))
const parent = computed(() =>
  detail.value?.parent_global_id ? (store.elementsById.get(detail.value.parent_global_id) ?? null) : null,
)
const parts = computed(() =>
  (detail.value?.part_global_ids ?? []).map((id) => store.elementsById.get(id)).filter((e) => !!e),
)
const partsCarbon = computed(() => parts.value.reduce((sum, p) => sum + (p?.carbon_kgco2e ?? 0), 0))

function display(value: unknown): string {
  if (value === null || value === undefined) return '–'
  if (typeof value === 'number') return formatNumber(value, 3)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

async function copyLink() {
  await navigator.clipboard?.writeText(window.location.href)
  store.notice = 'Link to this element copied'
}
</script>

<template>
  <div v-if="!element" class="flex flex-col items-center gap-2 py-10 text-center text-sm text-ink-300">
    <Icon name="cube" :size="28" class="text-ink-500" />
    Click an element in the 3D view, or pick one from the Elements tab, to see its layers, properties and carbon.
  </div>
  <div v-else class="space-y-4 text-sm">
    <header class="flex items-start gap-3">
      <span class="mt-1.5 h-3 w-3 shrink-0 rounded-sm" :style="{ background: colorOf(element.material_category) }" />
      <div class="min-w-0 flex-1">
        <h2 class="truncate text-base font-semibold" :title="element.name ?? element.global_id">{{ element.name ?? element.global_id }}</h2>
        <div class="mt-1 flex flex-wrap gap-1.5 text-[11px]">
          <span class="pill">{{ element.ifc_class }}</span>
          <span v-if="element.storey" class="pill">{{ element.storey }}</span>
          <span v-if="detail?.predefined_type" class="pill">{{ detail.predefined_type }}</span>
          <span v-if="element.type_name" class="pill">{{ element.type_name }}</span>
        </div>
      </div>
      <div class="flex shrink-0 gap-0.5">
        <button class="tool" title="Copy a link to this element" aria-label="Copy link" @click="copyLink"><Icon name="link" /></button>
        <button class="tool" title="Zoom to element" aria-label="Zoom to element" @click="viewerBridge.fit([element.global_id])"><Icon name="fit" /></button>
        <button class="tool" title="Clear selection" aria-label="Clear selection" @click="store.select(null, false)"><Icon name="close" /></button>
      </div>
    </header>

    <button
      v-if="parent"
      class="flex w-full items-center gap-2 rounded-lg border border-ink-700 px-3 py-2 text-left text-xs text-ink-300 hover:border-ink-500 hover:text-ink-100"
      @click="store.select(parent.global_id)"
    >
      <Icon name="layers" :size="14" /> Part of <span class="truncate font-medium text-ink-100">{{ parent.name ?? parent.ifc_class }}</span>
    </button>

    <!-- assemblies: the carbon sits in the parts -->
    <section v-if="element.is_assembly" class="rounded-lg border border-ink-700 p-3 text-xs">
      <div class="flex items-baseline justify-between">
        <span class="section-title">{{ parts.length }} parts</span>
        <span class="font-mono text-good">{{ formatCarbon(partsCarbon) }}</span>
      </div>
      <p class="mt-1 text-ink-500">An assembly has no material of its own; its carbon is the sum of its parts.</p>
      <ul class="mt-2 max-h-56 divide-y divide-ink-700/70 overflow-auto rounded-md border border-ink-700">
        <li v-for="p in parts" :key="p!.global_id">
          <button class="flex w-full items-center gap-2 px-2.5 py-1.5 text-left hover:bg-ink-700/60" @click="store.select(p!.global_id)">
            <span class="h-2 w-2 shrink-0 rounded-sm" :style="{ background: colorOf(p!.material_category) }" />
            <span class="flex-1 truncate text-ink-100">{{ p!.name ?? p!.global_id }}</span>
            <span class="font-mono text-ink-300">{{ formatCarbon(p!.carbon_kgco2e) }}</span>
          </button>
        </li>
      </ul>
    </section>

    <template v-else>
      <div class="grid grid-cols-3 gap-2 text-xs">
        <div class="rounded-lg border border-ink-700 bg-ink-900/60 p-2.5">
          <div class="text-ink-500">Carbon</div>
          <div class="mt-0.5 font-mono text-base text-good">{{ formatCarbon(element.carbon_kgco2e) }}</div>
        </div>
        <div class="rounded-lg border border-ink-700 bg-ink-900/60 p-2.5">
          <div class="text-ink-500">Mass</div>
          <div class="mt-0.5 font-mono text-base">{{ element.mass_kg !== null ? formatCarbon(element.mass_kg) : '–' }}</div>
        </div>
        <div class="rounded-lg border border-ink-700 bg-ink-900/60 p-2.5">
          <div class="flex items-center justify-between text-ink-500">
            <span>Volume</span>
          </div>
          <div class="mt-0.5 font-mono text-base">{{ formatNumber(element.volume_m3, 3) }}<span class="text-[10px] text-ink-500"> m³</span></div>
        </div>
      </div>
      <div v-if="element.volume_source" class="-mt-2 text-[11px] text-ink-500">
        Volume from
        {{ element.volume_source === 'quantity' ? 'the model’s base quantities' : 'the tessellated geometry' }}.
      </div>

      <!-- layers -->
      <section class="rounded-lg border border-ink-700 p-3 text-xs">
        <div class="mb-2 flex items-baseline justify-between">
          <span class="section-title">{{ layers.length > 1 ? `${layers.length} materials` : 'Material' }}</span>
          <span v-if="element.partially_classified" class="flex items-center gap-1 text-warn"><Icon name="warning" :size="12" /> partly classified</span>
        </div>
        <div v-if="layers.length > 1 && layerTotal" class="mb-3 flex h-2.5 overflow-hidden rounded-full bg-ink-700">
          <span
            v-for="(layer, i) in layers"
            :key="i"
            :style="{ width: `${((layer.volume_m3 ?? 0) / layerTotal) * 100}%`, background: colorOf(layer.category) }"
            :title="layer.material"
          />
        </div>
        <div v-if="!layers.length" class="text-ink-500">No material assigned in the model.</div>
        <ul class="space-y-2.5">
          <li v-for="(layer, i) in layers" :key="i">
            <div class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: colorOf(layer.category) }" />
              <span class="min-w-0 flex-1 truncate text-ink-100" :title="layer.material">{{ layer.material }}</span>
              <span class="shrink-0 font-mono" :class="layer.carbon_kgco2e ? 'text-ink-200' : 'text-ink-500'">{{ formatCarbon(layer.carbon_kgco2e) }}</span>
            </div>
            <div class="ml-[18px] mt-0.5 text-[11px] text-ink-500">
              <span :class="layer.category ? '' : 'text-warn'">{{ layer.category ? (store.factorLabels[layer.category] ?? layer.category) : 'Unclassified' }}</span>
              <template v-if="layer.thickness_m"> · {{ formatNumber(layer.thickness_m * 1000, 0) }} mm</template>
              <template v-if="layer.fraction !== null && layers.length > 1"> · {{ formatPercent(layer.fraction) }}</template>
            </div>
            <div v-if="layer.volume_m3 && factorFor(layer.category)" class="ml-[18px] mt-0.5 font-mono text-[10px] text-ink-500">
              {{ formatNumber(layer.volume_m3, 3) }} m³ × {{ factorFor(layer.category)!.density_kg_m3 }} kg/m³ ×
              {{ factorFor(layer.category)!.factor_kgco2e_per_kg }} kgCO₂e/kg
            </div>
          </li>
        </ul>
        <button
          v-if="layers.some((l) => !l.category)"
          class="mt-3 text-[11px] font-medium text-accent hover:underline"
          @click="store.activeTab = 'materials'"
        >
          Map unclassified materials →
        </button>
      </section>
    </template>

    <section class="text-xs">
      <div class="section-title mb-1">Identity</div>
      <dl class="grid grid-cols-[100px_1fr] gap-y-1">
        <dt class="text-ink-500">GlobalId</dt>
        <dd class="break-all font-mono">{{ element.global_id }}</dd>
        <dt class="text-ink-500">Express id</dt>
        <dd class="font-mono">#{{ element.express_id }}</dd>
        <template v-if="detail?.object_type">
          <dt class="text-ink-500">Object type</dt>
          <dd>{{ detail.object_type }}</dd>
        </template>
        <template v-if="detail?.description">
          <dt class="text-ink-500">Description</dt>
          <dd>{{ detail.description }}</dd>
        </template>
      </dl>
    </section>

    <template v-if="detail">
      <details
        v-for="(props, name) in { ...detail.quantity_sets, ...detail.property_sets }"
        :key="name"
        class="group rounded-lg border border-ink-700 text-xs"
        open
      >
        <summary class="flex cursor-pointer list-none items-center justify-between px-3 py-2 font-medium text-ink-100">
          {{ name }}
          <Icon name="chevron" :size="14" class="text-ink-300 transition group-open:rotate-180" />
        </summary>
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
