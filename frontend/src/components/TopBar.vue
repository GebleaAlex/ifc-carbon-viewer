<script setup lang="ts">
import { computed, ref } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { api } from '../api/client'
import { formatBytes, formatCarbon, formatIntensity } from '../lib/colors'
import { confirmDialog } from '../lib/confirm'
import { viewerBridge } from '../lib/viewerBridge'
import UiSelect from './ui/UiSelect.vue'
import MenuButton from './ui/MenuButton.vue'
import type { MenuItem, SelectOption } from './ui/types'
import Icon from './ui/Icon.vue'

const store = useViewerStore()
const fileInput = ref<HTMLInputElement | null>(null)
const emit = defineEmits<{ help: [] }>()

const modelOptions = computed<SelectOption<string>[]>(() =>
  store.models.map((m) => ({
    value: m.id,
    label: m.is_sample ? `${m.name} (sample)` : m.name,
    sub:
      m.status === 'ready'
        ? `${m.schema_version} · ${m.element_count} elements · ${formatCarbon(m.total_kgco2e)} CO₂e`
        : m.status === 'processing'
          ? 'Parsing…'
          : `Failed: ${m.error ?? 'unknown error'}`,
    disabled: m.status !== 'ready',
  })),
)

function onFileChosen(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) store.upload(file)
  if (fileInput.value) fileInput.value.value = ''
}

function download(href: string, filename?: string) {
  const a = document.createElement('a')
  a.href = href
  if (filename) a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

const exportItems = computed<MenuItem[]>(() => {
  const model = store.currentModel
  const stem = model?.name.replace(/\.ifc$/i, '') ?? 'model'
  return [
    {
      label: 'Element table (CSV)',
      sub: 'One row per element and material layer',
      icon: 'file',
      disabled: !model,
      action: () => model && download(api.csvUrl(model.id)),
    },
    {
      label: 'Carbon report (JSON)',
      sub: 'Totals, breakdowns and material mapping',
      icon: 'file',
      disabled: !model,
      action: () => model && download(api.reportUrl(model.id), `${stem}-report.json`),
    },
    {
      label: 'Screenshot (PNG)',
      sub: 'The 3D view as you see it',
      icon: 'camera',
      disabled: !model,
      action: () => {
        const url = viewerBridge.screenshot()
        if (url) download(url, `${stem}.png`)
      },
    },
  ]
})

async function onDelete() {
  const model = store.currentModel
  if (!model) return
  const ok = await confirmDialog({
    title: `Delete “${model.name}”?`,
    message: 'The IFC file, its geometry and the material mapping are removed from the server.',
    confirm: 'Delete model',
    danger: true,
  })
  if (ok) await store.removeModel(model.id)
}
</script>

<template>
  <header class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-ink-700/80 bg-ink-900/70 px-4 py-2.5 backdrop-blur">
    <div class="flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" class="h-8 w-8" />
      <div class="leading-tight">
        <div class="text-sm font-semibold tracking-tight">IFC Carbon Viewer</div>
        <div class="text-[11px] text-ink-300">Embodied carbon for BIM models</div>
      </div>
    </div>

    <div class="mx-1 hidden h-7 w-px bg-ink-700 sm:block" />

    <div class="w-[min(320px,60vw)]">
      <UiSelect
        :model-value="store.currentId"
        :options="modelOptions"
        label="Model"
        :placeholder="store.models.length ? 'Choose a model' : 'No models yet'"
        :disabled="!store.models.length"
        :min-width="340"
        @change="(id) => store.selectModel(id)"
      />
    </div>

    <div v-if="store.currentModel" class="hidden items-center gap-1.5 text-[11px] text-ink-300 xl:flex">
      <span class="pill">{{ store.currentModel.schema_version }}</span>
      <span class="pill">{{ store.currentModel.element_count }} elements</span>
      <span v-if="store.currentModel.length_unit" class="pill" title="Length unit of the file">{{ store.currentModel.length_unit }}</span>
      <span class="pill">{{ formatBytes(store.currentModel.file_size_bytes) }}</span>
      <span class="pill">{{ store.currentModel.parse_seconds }}s</span>
    </div>

    <div class="ml-auto flex items-center gap-2">
      <div v-if="store.currentModel" class="mr-1 hidden text-right leading-tight md:block">
        <div class="font-mono text-sm font-semibold text-good">{{ formatCarbon(store.currentModel.total_kgco2e) }} CO₂e</div>
        <div class="text-[11px] text-ink-300">
          <template v-if="store.currentModel.intensity_kgco2e_m2 !== null">
            {{ formatIntensity(store.currentModel.intensity_kgco2e_m2).replace(' kg/m²', '') }} kgCO₂e/m²
          </template>
          <template v-else>no floor area</template>
        </div>
      </div>
      <button class="btn icon-btn hidden sm:inline-flex" title="Keyboard shortcuts (?)" aria-label="Keyboard shortcuts" @click="emit('help')">
        <Icon name="keyboard" />
      </button>
      <MenuButton label="Export" icon="download" :items="exportItems" />
      <button
        v-if="store.currentModel && !store.currentModel.is_sample"
        class="btn icon-btn"
        title="Delete this model"
        aria-label="Delete this model"
        @click="onDelete"
      >
        <Icon name="trash" />
      </button>
      <button class="btn btn-primary" :disabled="store.uploading" @click="fileInput?.click()">
        <svg v-if="store.uploading" class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-opacity="0.3" stroke-width="3" />
          <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
        </svg>
        <Icon v-else name="upload" />
        {{ store.uploading ? (store.uploadProgress !== null ? `Uploading ${Math.round(store.uploadProgress * 100)}%` : 'Parsing…') : 'Open IFC' }}
      </button>
      <input ref="fileInput" type="file" accept=".ifc" class="hidden" @change="onFileChosen" />
    </div>
  </header>
</template>
