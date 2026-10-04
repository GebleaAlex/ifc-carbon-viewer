<script setup lang="ts">
import { computed, ref } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { UNCLASSIFIED } from '../lib/aggregate'
import { UNCLASSIFIED_COLOR, formatCarbon, formatNumber } from '../lib/colors'
import { confirmDialog } from '../lib/confirm'
import type { SelectOption } from './ui/types'
import UiSelect from './ui/UiSelect.vue'
import Icon from './ui/Icon.vue'

// Every material name in the model, how the keyword rules classified it and a way to correct them.
// Changes are stored per model on the server and recomputed there, so exports include them.
const store = useViewerStore()
const query = ref('')

const options = computed<SelectOption<string>[]>(() => [
  ...store.factors.map((f) => ({
    value: f.category,
    label: f.label,
    sub: `${f.density_kg_m3} kg/m³ · ${f.factor_kgco2e_per_kg} kgCO₂e/kg`,
    color: f.color,
  })),
  { value: UNCLASSIFIED, label: 'Unclassified', sub: 'Leave out of the estimate', color: UNCLASSIFIED_COLOR },
])

const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  return store.materials.filter((m) => !q || m.material.toLowerCase().includes(q))
})
const unclassified = computed(() => store.materials.filter((m) => !m.category).length)
const overridden = computed(() => store.materials.filter((m) => m.overridden).length)

async function resetAll() {
  const ok = await confirmDialog({
    title: 'Reset all material mappings?',
    message: `${overridden.value === 1 ? 'Your manual choice goes' : `${overridden.value} manual choices go`} back to the automatic classification.`,
    confirm: 'Reset mappings',
  })
  if (ok) await store.saveOverrides({})
}
</script>

<template>
  <div v-if="!store.currentId" class="text-sm text-ink-300">Load a model to see its materials.</div>
  <div v-else class="space-y-3">
    <div class="rounded-xl border border-ink-700 bg-ink-900/60 p-3 text-xs leading-relaxed text-ink-300">
      Materials are matched to the factor table by keyword. Correct any match here; the estimate, charts and exports
      update straight away.
      <div class="mt-2 flex flex-wrap items-center gap-1.5">
        <span class="pill">{{ store.materials.length }} materials</span>
        <span v-if="unclassified" class="pill border-warn/40 text-warn">{{ unclassified }} unclassified</span>
        <span v-if="overridden" class="pill border-accent/40 text-accent">{{ overridden }} mapped by hand</span>
        <span v-if="store.savingMapping" class="ml-auto flex items-center gap-1.5 text-accent">
          <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> Recalculating…
        </span>
        <button v-else-if="overridden" class="ml-auto flex items-center gap-1 text-ink-300 hover:text-ink-100" @click="resetAll">
          <Icon name="reset" :size="13" /> Reset all
        </button>
      </div>
    </div>

    <div class="flex items-center gap-2 rounded-lg border border-ink-600 bg-ink-900 px-2.5 focus-within:border-accent">
      <Icon name="search" :size="14" class="text-ink-300" />
      <input v-model="query" type="search" placeholder="Search materials…" class="h-8 w-full bg-transparent text-sm outline-none placeholder:text-ink-500" />
    </div>

    <ul class="space-y-2">
      <li
        v-for="m in rows"
        :key="m.material"
        class="rounded-lg border bg-ink-900/40 p-2.5"
        :class="m.category ? 'border-ink-700' : 'border-warn/40'"
      >
        <div class="flex items-start gap-2">
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm text-ink-100" :title="m.material">{{ m.material }}</div>
            <div class="mt-0.5 text-[11px] text-ink-500">
              {{ m.element_count }} element{{ m.element_count === 1 ? '' : 's' }} · {{ formatNumber(m.volume_m3, 2, 'm³') }}
              <template v-if="m.ifc_category"> · IFC category “{{ m.ifc_category }}”</template>
            </div>
          </div>
          <span class="shrink-0 font-mono text-xs" :class="m.category ? 'text-ink-200' : 'text-ink-500'">
            {{ m.category ? formatCarbon(m.carbon_kgco2e) : '–' }}
          </span>
        </div>
        <div class="mt-2 flex items-center gap-2">
          <div class="min-w-0 flex-1">
            <UiSelect
              :model-value="m.category ?? UNCLASSIFIED"
              :options="options"
              label="Category"
              size="sm"
              :disabled="store.savingMapping"
              @change="(value) => store.setMaterialCategory(m.material, value)"
            />
          </div>
          <span v-if="m.overridden" class="pill shrink-0 border-accent/40 py-0 text-[10px] text-accent">manual</span>
          <span v-else-if="m.category" class="pill shrink-0 py-0 text-[10px]">auto</span>
          <button
            v-if="m.overridden"
            class="tool h-7 shrink-0 px-1.5"
            :title="`Back to automatic (${m.auto_category ? (store.factorLabels[m.auto_category] ?? m.auto_category) : 'unclassified'})`"
            aria-label="Back to automatic"
            :disabled="store.savingMapping"
            @click="store.setMaterialCategory(m.material, null)"
          >
            <Icon name="reset" :size="14" />
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>
