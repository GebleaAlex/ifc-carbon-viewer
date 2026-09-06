<script setup lang="ts">
import { useViewerStore } from '../stores/viewer'
import { UNCLASSIFIED_COLOR, classColor, formatCarbon, formatNumber } from '../lib/colors'
import BarList from './BarList.vue'

const store = useViewerStore()
</script>

<template>
  <div v-if="!store.carbon" class="text-sm text-ink-300">Load a model to see its carbon breakdown.</div>
  <div v-else class="space-y-5">
    <div class="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-ink-300">Embodied carbon (A1–A3, indicative)</div>
      <div class="mt-1 flex items-baseline gap-2">
        <span class="text-3xl font-semibold tracking-tight text-good">{{ formatCarbon(store.carbon.total_kgco2e) }}</span>
        <span class="text-sm text-ink-300">CO₂e</span>
      </div>
      <dl class="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt class="text-ink-500">Estimated</dt>
          <dd class="font-mono text-ink-100">{{ store.carbon.estimated_elements }} / {{ store.elements.length }}</dd>
        </div>
        <div>
          <dt class="text-ink-500">Unclassified</dt>
          <dd class="font-mono" :class="store.carbon.unclassified_elements ? 'text-warn' : 'text-ink-100'">
            {{ store.carbon.unclassified_elements }}
          </dd>
        </div>
        <div>
          <dt class="text-ink-500">No volume</dt>
          <dd class="font-mono" :class="store.carbon.missing_volume_elements ? 'text-warn' : 'text-ink-100'">
            {{ store.carbon.missing_volume_elements }}
          </dd>
        </div>
      </dl>
    </div>

    <BarList
      title="By material"
      :buckets="store.carbon.by_material_category"
      :color-for="(b) => store.factorColors[b.key] ?? UNCLASSIFIED_COLOR"
    />
    <BarList title="By storey" :buckets="store.carbon.by_storey" />
    <BarList title="By IFC class" :buckets="store.carbon.by_ifc_class" :color-for="(b) => classColor(b.key)" />

    <section>
      <h3 class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-300">Largest contributors</h3>
      <ol class="divide-y divide-ink-700/70 rounded-lg border border-ink-700">
        <li v-for="el in store.carbon.top_elements" :key="el.global_id">
          <button
            class="flex w-full items-center gap-3 px-3 py-2 text-left text-xs transition hover:bg-ink-700/60"
            :class="store.selectedId === el.global_id ? 'bg-ink-700/80' : ''"
            @click="store.select(el.global_id)"
          >
            <span class="h-2 w-2 shrink-0 rounded-sm" :style="{ background: store.factorColors[el.material_category ?? ''] ?? UNCLASSIFIED_COLOR }" />
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
      Volumes come from IFC base quantities where present and from the tessellated geometry otherwise.
    </p>
  </div>
</template>
