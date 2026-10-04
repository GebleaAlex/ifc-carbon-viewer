<script setup lang="ts">
import { computed } from 'vue'
import { useViewerStore } from '../stores/viewer'
import type { CarbonBucket } from '../api/types'
import {
  UNCLASSIFIED_COLOR,
  classColor,
  formatArea,
  formatCarbon,
  formatNumber,
} from '../lib/colors'
import { UNCLASSIFIED, type FocusKind, type QualityIssue } from '../lib/aggregate'
import BarList from './BarList.vue'
import DonutChart from './charts/DonutChart.vue'
import StoreyStacks from './charts/StoreyStacks.vue'
import Icon from './ui/Icon.vue'

const store = useViewerStore()
const carbon = computed(() => store.carbon)

const materialColor = (key: string) =>
  key === UNCLASSIFIED ? UNCLASSIFIED_COLOR : (store.factorColors[key] ?? UNCLASSIFIED_COLOR)
const segments = computed(() =>
  (carbon.value?.by_material_category ?? []).map((b) => ({
    key: b.key,
    label: b.label,
    value: b.carbon_kgco2e,
    color: materialColor(b.key),
  })),
)

const activeKey = (kind: FocusKind) => (store.focus?.kind === kind ? store.focus.key : null)
function focusBucket(kind: FocusKind, bucket: CarbonBucket) {
  store.toggleFocus({ kind, key: bucket.key, label: bucket.label })
}

const issues = computed(() => {
  const c = carbon.value
  if (!c) return []
  const list: { key: QualityIssue; count: number; label: string; hint: string }[] = [
    {
      key: 'unclassified',
      count: c.unclassified_elements,
      label: 'unclassified',
      hint: 'No material matched the factor table. Map them in the Materials tab.',
    },
    {
      key: 'partial',
      count: c.partially_classified_elements,
      label: 'partly classified',
      hint: 'Some layers of these elements have no factor yet.',
    },
    {
      key: 'no-volume',
      count: c.missing_volume_elements,
      label: 'without volume',
      hint: 'No volume quantity and no closed geometry to measure.',
    },
  ]
  return list.filter((i) => i.count > 0)
})

const floorAreaNote = computed(() => {
  const source = carbon.value?.floor_area_source
  if (source === 'spaces') return 'from IfcSpace floor areas'
  if (source === 'slab quantities') return 'from floor slab areas'
  if (source === 'slab geometry') return 'measured from floor slabs'
  return null
})
</script>

<template>
  <div v-if="!carbon" class="text-sm text-ink-300">Load a model to see its carbon breakdown.</div>
  <div v-else class="space-y-6">
    <!-- headline numbers -->
    <div class="grid grid-cols-2 gap-2">
      <div class="col-span-2 rounded-xl border border-ink-700 bg-gradient-to-br from-ink-900 to-ink-800 p-4">
        <div class="section-title">Embodied carbon · A1–A3, indicative</div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-3xl font-semibold tracking-tight text-good">{{ formatCarbon(carbon.total_kgco2e) }}</span>
          <span class="text-sm text-ink-300">CO₂e</span>
        </div>
        <div class="mt-1 text-xs text-ink-300">
          {{ carbon.estimated_elements }} of {{ store.elements.length - carbon.assembly_elements }} elements estimated
        </div>
      </div>
      <div class="rounded-xl border border-ink-700 bg-ink-900/60 p-3">
        <div class="text-[11px] text-ink-300">Intensity</div>
        <div class="mt-0.5 font-mono text-lg text-ink-100">
          {{ carbon.intensity_kgco2e_m2 !== null ? formatNumber(carbon.intensity_kgco2e_m2, 0) : '–' }}
          <span class="text-xs text-ink-300">kg/m²</span>
        </div>
      </div>
      <div class="rounded-xl border border-ink-700 bg-ink-900/60 p-3">
        <div class="text-[11px] text-ink-300">Floor area</div>
        <div class="mt-0.5 font-mono text-lg text-ink-100">{{ formatArea(carbon.gross_floor_area_m2) }}</div>
        <div v-if="floorAreaNote" class="text-[10px] text-ink-500">{{ floorAreaNote }}</div>
      </div>
    </div>

    <!-- data quality -->
    <section>
      <h3 class="section-title mb-2">Data quality</h3>
      <div v-if="!issues.length" class="flex items-center gap-2 rounded-lg border border-good/30 bg-good/10 px-3 py-2 text-xs text-good">
        <Icon name="check" :size="14" /> Every element has a material and a volume.
      </div>
      <div v-else class="flex flex-wrap gap-1.5">
        <button
          v-for="issue in issues"
          :key="issue.key"
          class="chip border-warn/40 text-warn"
          :aria-pressed="store.focus?.kind === 'quality' && store.focus.key === issue.key"
          :title="issue.hint"
          @click="store.toggleFocus({ kind: 'quality', key: issue.key, label: `${issue.count} ${issue.label}` })"
        >
          <Icon name="warning" :size="13" /> {{ issue.count }} {{ issue.label }}
        </button>
        <button
          v-if="carbon.unclassified_elements || carbon.partially_classified_elements"
          class="chip"
          @click="store.activeTab = 'materials'"
        >
          Map materials →
        </button>
      </div>
    </section>

    <!-- materials -->
    <section>
      <h3 class="section-title mb-2">By material</h3>
      <div class="flex items-start gap-3">
      <DonutChart
        :segments="segments"
        :active-key="activeKey('material')"
        @select="(s) => store.toggleFocus({ kind: 'material', key: s.key, label: s.label })"
      />
      <ul class="min-w-0 flex-1 space-y-px text-xs">
        <li v-for="b in carbon.by_material_category" :key="b.key">
          <button
            class="flex w-full items-center gap-2 rounded px-1.5 py-0.5 text-left hover:bg-ink-700/60"
            :class="activeKey('material') === b.key ? 'bg-accent/10 text-accent' : 'text-ink-200'"
            @click="focusBucket('material', b)"
          >
            <span class="h-2 w-2 shrink-0 rounded-sm" :style="{ background: materialColor(b.key) }" />
            <span class="flex-1 truncate">{{ b.label }}</span>
            <span class="shrink-0 font-mono text-ink-200">{{ formatCarbon(b.carbon_kgco2e) }}</span>
            <span class="w-8 shrink-0 text-right font-mono text-[10px] text-ink-500">{{ Math.round(b.share_percent) }}%</span>
          </button>
        </li>
      </ul>
      </div>
    </section>
    <StoreyStacks />
    <BarList
      title="By IFC class"
      :buckets="carbon.by_ifc_class"
      :color-for="(b) => classColor(b.key)"
      :active-key="activeKey('class')"
      @select="(b) => focusBucket('class', b)"
    />

    <section>
      <h3 class="section-title mb-2">Largest contributors</h3>
      <ol class="divide-y divide-ink-700/70 rounded-lg border border-ink-700">
        <li v-for="(el, i) in carbon.top_elements" :key="el.global_id">
          <button
            class="flex w-full items-center gap-3 px-3 py-2 text-left text-xs transition hover:bg-ink-700/60"
            :class="store.selectedId === el.global_id ? 'bg-ink-700/80' : ''"
            @click="store.select(el.global_id)"
          >
            <span class="w-4 shrink-0 text-right font-mono text-ink-500">{{ i + 1 }}</span>
            <span class="h-2 w-2 shrink-0 rounded-sm" :style="{ background: materialColor(el.material_category ?? UNCLASSIFIED) }" />
            <span class="min-w-0 flex-1">
              <span class="block truncate text-ink-100">{{ el.name ?? el.global_id }}</span>
              <span class="block truncate text-ink-500">{{ el.ifc_class }} · {{ formatNumber(el.volume_m3, 2, 'm³') }}</span>
            </span>
            <span class="shrink-0 font-mono text-ink-200">{{ formatCarbon(el.carbon_kgco2e) }}</span>
          </button>
        </li>
      </ol>
    </section>

    <p class="text-[11px] leading-relaxed text-ink-500">
      Factors are generic order-of-magnitude values (see <span class="font-mono">factors.json</span>), not product EPDs.
      Volumes come from IFC base quantities where present and from the tessellated geometry otherwise, and are split
      across material layers by thickness. Assemblies such as curtain walls are counted through their parts.
    </p>
  </div>
</template>
