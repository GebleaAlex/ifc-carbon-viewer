<script setup lang="ts">
import { ref } from 'vue'
import { useViewerStore } from '../stores/viewer'
import { formatBytes, formatCarbon } from '../lib/colors'

const store = useViewerStore()
const fileInput = ref<HTMLInputElement | null>(null)

function onFileChosen(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) store.upload(file)
  if (fileInput.value) fileInput.value.value = ''
}

async function onDelete() {
  const model = store.currentModel
  if (!model) return
  if (window.confirm(`Delete "${model.name}" from the server?`)) await store.removeModel(model.id)
}
</script>

<template>
  <header class="flex items-center gap-4 border-b border-ink-700/80 bg-ink-900/70 px-4 py-2.5 backdrop-blur">
    <div class="flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" class="h-7 w-7" />
      <div class="leading-tight">
        <div class="text-sm font-semibold tracking-tight">IFC Carbon Viewer</div>
        <div class="text-[11px] text-ink-300">IfcOpenShell · FastAPI · Three.js</div>
      </div>
    </div>

    <div class="mx-2 hidden h-6 w-px bg-ink-700 sm:block" />

    <label class="flex items-center gap-2 text-sm">
      <span class="hidden text-ink-300 sm:inline">Model</span>
      <select
        class="max-w-[260px] truncate rounded-lg border border-ink-600 bg-ink-800 px-2.5 py-1.5 text-sm text-ink-100 outline-none focus:border-accent"
        :value="store.currentId ?? ''"
        :disabled="!store.models.length"
        @change="store.selectModel(($event.target as HTMLSelectElement).value)"
      >
        <option v-if="!store.models.length" value="">No models yet</option>
        <option v-for="m in store.models" :key="m.id" :value="m.id" :disabled="m.status !== 'ready'">
          {{ m.name }}{{ m.is_sample ? ' (sample)' : '' }}{{ m.status !== 'ready' ? ` · ${m.status}` : '' }}
        </option>
      </select>
    </label>

    <div v-if="store.currentModel" class="hidden items-center gap-2 text-[11px] text-ink-300 md:flex">
      <span class="pill">{{ store.currentModel.schema_version }}</span>
      <span class="pill">{{ store.currentModel.element_count }} elements</span>
      <span class="pill">{{ formatBytes(store.currentModel.file_size_bytes) }}</span>
      <span class="pill">parsed in {{ store.currentModel.parse_seconds }}s</span>
      <span class="pill border-good/40 text-good">{{ formatCarbon(store.currentModel.total_kgco2e) }} CO₂e</span>
    </div>

    <div class="ml-auto flex items-center gap-2">
      <button
        v-if="store.currentModel && !store.currentModel.is_sample"
        class="btn"
        title="Delete this model from the server"
        @click="onDelete"
      >
        Delete
      </button>
      <button class="btn btn-primary" :disabled="store.uploading" @click="fileInput?.click()">
        <svg v-if="store.uploading" class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-opacity="0.3" stroke-width="3" />
          <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
        </svg>
        {{ store.uploading ? 'Parsing…' : 'Open IFC' }}
      </button>
      <input ref="fileInput" type="file" accept=".ifc" class="hidden" @change="onFileChosen" />
    </div>
  </header>
</template>
