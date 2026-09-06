<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import { useViewerStore } from '../stores/viewer'
import { Viewer } from '../three/Viewer'
import ViewToolbar from './ViewToolbar.vue'
import Legend from './Legend.vue'
import { formatCarbon } from '../lib/colors'

const store = useViewerStore()
const host = ref<HTMLDivElement | null>(null)
const tooltip = ref({ x: 0, y: 0 })
const geometryLoading = ref(false)
let viewer: Viewer | null = null

onMounted(() => {
  if (!host.value) return
  viewer = new Viewer(host.value, {
    onHover: ({ globalId, clientX, clientY }) => {
      store.hoveredId = globalId
      const rect = host.value!.getBoundingClientRect()
      tooltip.value = { x: clientX - rect.left, y: clientY - rect.top }
    },
    onSelect: ({ globalId }) => store.select(globalId),
  })
  if (import.meta.env.DEV) (window as unknown as { __viewer?: Viewer }).__viewer = viewer
  void loadGeometry(store.currentId)
})

onBeforeUnmount(() => {
  viewer?.dispose()
  viewer = null
})

async function loadGeometry(id: string | null) {
  if (!viewer) return
  if (!id) {
    viewer.clear()
    return
  }
  geometryLoading.value = true
  try {
    await viewer.load(api.geometryUrl(id))
    viewer.applyColors((gid) => store.colorFor(gid))
    viewer.setVisibility((gid) => store.isVisible(gid))
    viewer.setSelected(store.selectedId)
  } catch (e) {
    store.error = e instanceof Error ? e.message : String(e)
  } finally {
    geometryLoading.value = false
  }
}

watch(() => store.currentId, loadGeometry)

watch(
  () => [store.colorMode, store.maxCarbon, store.factorColors],
  () => viewer?.applyColors((gid) => store.colorFor(gid)),
)

watch(
  () => [store.hiddenStoreys, store.hiddenClasses],
  () => viewer?.setVisibility((gid) => store.isVisible(gid)),
)

watch(
  () => store.selectedId,
  (id) => viewer?.setSelected(id),
)

function fit() {
  viewer?.fitToView()
}

function fitSelection() {
  if (store.selectedId) viewer?.fitToView([store.selectedId])
}

defineExpose({ fit, fitSelection })
</script>

<template>
  <section class="viewer-bg panel relative min-h-[420px] overflow-hidden">
    <div ref="host" class="absolute inset-0" />

    <ViewToolbar class="absolute left-3 top-3" @fit="fit" @fit-selection="fitSelection" />
    <Legend class="absolute bottom-3 left-3" />

    <div
      v-if="store.hoveredElement"
      class="pointer-events-none absolute z-10 max-w-xs rounded-lg border border-ink-600 bg-ink-900/95 px-3 py-2 text-xs shadow-xl"
      :style="{ left: `${tooltip.x + 14}px`, top: `${tooltip.y + 14}px` }"
    >
      <div class="font-medium text-ink-100">{{ store.hoveredElement.name ?? store.hoveredElement.global_id }}</div>
      <div class="mt-0.5 text-ink-300">
        {{ store.hoveredElement.ifc_class }}<span v-if="store.hoveredElement.storey"> · {{ store.hoveredElement.storey }}</span>
      </div>
      <div class="mt-1 flex items-center gap-2">
        <span class="text-ink-300">{{ store.hoveredElement.materials[0] ?? 'No material' }}</span>
        <span class="ml-auto font-mono text-good">{{ formatCarbon(store.hoveredElement.carbon_kgco2e) }}</span>
      </div>
    </div>

    <div
      v-if="geometryLoading || store.loading"
      class="absolute inset-0 z-20 flex items-center justify-center bg-ink-950/40 backdrop-blur-[2px]"
    >
      <div class="flex items-center gap-3 rounded-xl border border-ink-600 bg-ink-800 px-4 py-3 text-sm">
        <span class="h-2 w-2 animate-pulse rounded-full bg-accent" /> Loading geometry…
      </div>
    </div>

    <div
      v-else-if="!store.currentId && !store.uploading"
      class="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 text-center"
    >
      <div class="text-lg font-semibold">No model loaded</div>
      <p class="max-w-sm text-sm text-ink-300">
        Drop an <span class="font-mono text-ink-100">.ifc</span> file anywhere on this page, or use
        <span class="text-ink-100">Open IFC</span> in the header. Parsing happens on the server with IfcOpenShell.
      </p>
    </div>

    <div class="absolute bottom-3 right-3 hidden text-[10px] text-ink-500 md:block">
      drag to orbit · right-drag to pan · wheel to zoom · click to select
    </div>
  </section>
</template>
