<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import { useViewerStore } from '../stores/viewer'
import { Viewer } from '../three/Viewer'
import { registerViewer, viewerBridge } from '../lib/viewerBridge'
import { formatCarbon } from '../lib/colors'
import { matchesFocus } from '../lib/aggregate'
import ViewToolbar from './ViewToolbar.vue'
import Legend from './Legend.vue'
import Icon from './ui/Icon.vue'

const store = useViewerStore()
const host = ref<HTMLDivElement | null>(null)
// The tooltip belongs to the pointer: it only shows for elements hovered in the 3D view itself.
// Rows hovered in the Elements list highlight their element instead (store.hoveredId).
const tooltip = ref<{ id: string | null; x: number; y: number; width: number; height: number }>({
  id: null,
  x: 0,
  y: 0,
  width: 0,
  height: 0,
})
const geometryLoading = ref(false)
let viewer: Viewer | null = null

onMounted(() => {
  if (!host.value) return
  viewer = new Viewer(host.value, {
    onHover: ({ globalId, clientX, clientY }) => {
      store.hoveredId = globalId
      const rect = host.value!.getBoundingClientRect()
      tooltip.value = {
        id: globalId,
        x: clientX - rect.left,
        y: clientY - rect.top,
        width: rect.width,
        height: rect.height,
      }
    },
    onSelect: ({ globalId }) => store.select(globalId),
  })
  registerViewer(viewer)
  if (import.meta.env.DEV) (window as unknown as { __viewer?: Viewer }).__viewer = viewer
  void loadGeometry(store.currentId)
})

onBeforeUnmount(() => {
  registerViewer(null)
  viewer?.dispose()
  viewer = null
})

function paintAll() {
  viewer?.applyColors(
    (gid) => store.colorFor(gid),
    (gid) => store.opacityFor(gid),
  )
}

async function loadGeometry(id: string | null) {
  if (!viewer) return
  if (!id) {
    viewer.clear()
    return
  }
  geometryLoading.value = true
  try {
    await viewer.load(api.geometryUrl(id))
    if (id !== store.currentId) return // another model was chosen while this one was downloading
    paintAll()
    viewer.setVisibility((gid) => store.isVisible(gid))
    viewer.setGhosted((gid) => store.isGhosted(gid))
    viewer.setSelected(store.selectedId)
    viewer.setSection(store.sectionEnabled, store.sectionHeight)
  } catch (e) {
    if (id === store.currentId) store.error = `The 3D geometry could not be loaded: ${e instanceof Error ? e.message : String(e)}`
  } finally {
    if (id === store.currentId) geometryLoading.value = false
  }
}

watch(() => store.currentId, loadGeometry)
watch(() => [store.colorMode, store.maxCarbon, store.factorColors, store.elements], paintAll)
watch(
  () => [store.hiddenStoreys, store.hiddenClasses, store.hiddenIds, store.isolatedIds],
  () => viewer?.setVisibility((gid) => store.isVisible(gid)),
)
watch(
  () => [store.focus, store.xray, store.selectedId, store.elements],
  () => viewer?.setGhosted((gid) => store.isGhosted(gid)),
)
watch(
  () => store.selectedId,
  (id) => viewer?.setSelected(id),
)
watch(
  () => store.hoveredId,
  (id) => viewer?.setHighlighted(id),
)
watch(
  () => [store.sectionEnabled, store.sectionHeight] as const,
  ([enabled, height]) => viewer?.setSection(enabled, height),
)
// Isolating jumps to what is left; clearing the isolation goes back to the whole model.
watch(
  () => store.isolatedIds,
  (ids) => viewer?.fitToView(ids ? [...ids] : undefined),
)

const focusCount = computed(() =>
  store.focus ? store.elements.filter((e) => !e.is_assembly && matchesFocus(e, store.focus)).length : 0,
)

const hovered = computed(() => (tooltip.value.id ? (store.elementsById.get(tooltip.value.id) ?? null) : null))
// Near the right or bottom edge the tooltip flips to the other side of the pointer instead of being cut off.
const tooltipStyle = computed(() => {
  const { x, y, width, height } = tooltip.value
  return {
    ...(x > width - 240 ? { right: `${width - x + 12}px` } : { left: `${x + 14}px` }),
    ...(y > height - 110 ? { bottom: `${height - y + 12}px` } : { top: `${y + 14}px` }),
  }
})
const selected = computed(() => store.selectedElement)
</script>

<template>
  <section class="viewer-bg panel relative min-h-[360px] overflow-hidden" aria-label="3D view">
    <div ref="host" class="absolute inset-0" />

    <ViewToolbar class="absolute left-2 top-2 z-10 max-w-[calc(100%-3.75rem)] sm:left-3 sm:top-3 sm:max-w-[calc(100%-4.5rem)]" />

    <!-- camera and view tools -->
    <div class="toolbar absolute right-2 top-2 z-10 flex-col sm:right-3 sm:top-3">
      <button class="tool" title="Fit to view (F)" aria-label="Fit to view" @click="viewerBridge.fit()"><Icon name="fit" /></button>
      <button class="tool" title="Isometric view" aria-label="Isometric view" @click="viewerBridge.setView('iso')"><Icon name="cube" /></button>
      <button class="tool" title="Top view" aria-label="Top view" @click="viewerBridge.setView('top')"><Icon name="top" /></button>
      <button class="tool" title="Front view" aria-label="Front view" @click="viewerBridge.setView('front')"><Icon name="front" /></button>
      <button class="tool" title="Side view" aria-label="Side view" @click="viewerBridge.setView('side')"><Icon name="side" /></button>
      <div class="my-1 h-px w-6 bg-ink-700" />
      <button
        class="tool"
        title="Section cut (S)"
        aria-label="Section cut"
        :aria-pressed="store.sectionEnabled"
        @click="store.sectionEnabled = !store.sectionEnabled"
      >
        <Icon name="section" />
      </button>
      <button class="tool" title="X-ray (X)" aria-label="X-ray" :aria-pressed="store.xray" @click="store.xray = !store.xray">
        <Icon name="xray" />
      </button>
      <button
        v-if="store.hiddenCount"
        class="tool text-warn"
        title="Show everything (Shift+H)"
        aria-label="Show everything"
        @click="store.showAll()"
      >
        <Icon name="eye" />
      </button>
      <button
        class="tool hidden lg:inline-flex"
        :title="store.panelCollapsed ? 'Show the side panel (P)' : 'Hide the side panel (P)'"
        aria-label="Hide the side panel"
        :aria-pressed="store.panelCollapsed"
        @click="store.panelCollapsed = !store.panelCollapsed"
      >
        <Icon name="panel" />
      </button>
    </div>

    <!-- focus banner -->
    <Transition name="pop">
      <div
        v-if="store.focus"
        class="absolute left-1/2 top-24 z-10 flex max-w-[calc(100%-5rem)] -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-full border border-accent/40 bg-ink-900/90 py-1 pl-3 pr-1 text-xs shadow-lg backdrop-blur sm:top-14"
        role="status"
      >
        <span class="hidden text-ink-300 sm:inline">Showing</span>
        <span class="min-w-0 truncate font-medium text-ink-100">{{ store.focus.label }}</span>
        <span class="text-ink-300">· {{ focusCount }} element{{ focusCount === 1 ? '' : 's' }}</span>
        <button class="tool h-6 px-1.5" aria-label="Clear focus" title="Clear (Esc)" @click="store.focus = null"><Icon name="close" :size="14" /></button>
      </div>
    </Transition>

    <!-- bottom row: the legend on the left, selection actions and the section slider stacked beside it -->
    <div class="pointer-events-none absolute inset-x-2 bottom-2 z-10 flex items-end gap-3 sm:inset-x-3 sm:bottom-3">
    <Legend class="pointer-events-auto hidden shrink-0 sm:block" />
    <div class="flex min-w-0 flex-1 flex-col items-center gap-2">
    <!-- selection quick actions -->
    <Transition name="pop">
      <div v-if="selected" class="toolbar pointer-events-auto max-w-full gap-1 pl-3">
        <span class="mr-1 min-w-0 max-w-[220px] truncate text-xs font-medium text-ink-100">{{ selected.name ?? selected.global_id }}</span>
        <button class="tool" title="Zoom to selection (Z)" aria-label="Zoom to selection" @click="viewerBridge.fit([selected.global_id])">
          <Icon name="fit" :size="14" /> <span class="max-[400px]:hidden">Zoom</span>
        </button>
        <button class="tool" title="Isolate (I)" aria-label="Isolate" @click="store.isolateSelected()">
          <Icon name="isolate" :size="14" /> <span class="max-[400px]:hidden">Isolate</span>
        </button>
        <button class="tool" title="Hide (H)" aria-label="Hide" @click="store.hideSelected()">
          <Icon name="eyeOff" :size="14" /> <span class="max-[400px]:hidden">Hide</span>
        </button>
        <button class="tool" title="Clear selection (Esc)" aria-label="Clear selection" @click="store.select(null, false)"><Icon name="close" :size="14" /></button>
      </div>
    </Transition>

    <!-- section slider -->
    <Transition name="pop">
      <div v-if="store.sectionEnabled" class="toolbar pointer-events-auto w-[min(340px,100%)] gap-3 px-3 py-2">
        <Icon name="section" class="text-accent" />
        <input
          v-model.number="store.sectionHeight"
          class="slider"
          type="range"
          min="0"
          max="1"
          step="0.005"
          aria-label="Section height"
        />
        <span class="w-9 shrink-0 text-right font-mono text-[11px] text-ink-300">{{ Math.round(store.sectionHeight * 100) }}%</span>
        <button class="tool h-6 shrink-0 px-1.5" title="Turn the section cut off (S)" aria-label="Turn the section cut off" @click="store.sectionEnabled = false">
          <Icon name="close" :size="14" />
        </button>
      </div>
    </Transition>
    </div>
    </div>

    <div
      v-if="hovered"
      class="pointer-events-none absolute z-20 max-w-xs rounded-lg border border-ink-600 bg-ink-900/95 px-3 py-2 text-xs shadow-xl"
      :style="tooltipStyle"
    >
      <div class="font-medium text-ink-100">{{ hovered.name ?? hovered.global_id }}</div>
      <div class="mt-0.5 text-ink-300">
        {{ hovered.ifc_class }}<span v-if="hovered.storey"> · {{ hovered.storey }}</span>
      </div>
      <div class="mt-1 flex items-center gap-2">
        <span class="truncate text-ink-300">
          {{ hovered.layers.length > 1 ? `${hovered.layers.length} layers` : (hovered.materials[0] ?? 'No material') }}
        </span>
        <span class="ml-auto font-mono text-good">{{ formatCarbon(hovered.carbon_kgco2e) }}</span>
      </div>
    </div>

    <div
      v-if="geometryLoading || store.loading"
      class="absolute inset-0 z-30 flex items-center justify-center bg-ink-950/40 backdrop-blur-[2px]"
    >
      <div class="flex items-center gap-3 rounded-xl border border-ink-600 bg-ink-800 px-4 py-3 text-sm">
        <span class="h-2 w-2 animate-pulse rounded-full bg-accent" /> {{ geometryLoading ? 'Loading geometry…' : 'Loading model…' }}
      </div>
    </div>

    <div
      v-else-if="store.uploading"
      class="absolute inset-0 z-30 flex items-center justify-center bg-ink-950/50 backdrop-blur-[2px]"
    >
      <div class="w-72 rounded-xl border border-ink-600 bg-ink-800 px-4 py-3 text-sm shadow-xl">
        <div class="truncate font-medium">{{ store.uploadName }}</div>
        <div class="mt-0.5 text-xs text-ink-300">
          {{ store.uploadProgress !== null ? 'Uploading…' : 'Parsing with IfcOpenShell…' }}
        </div>
        <div class="mt-2.5 h-1.5 overflow-hidden rounded-full bg-ink-700">
          <div
            v-if="store.uploadProgress !== null"
            class="h-full rounded-full bg-accent transition-all"
            :style="{ width: `${Math.round(store.uploadProgress * 100)}%` }"
          />
          <div v-else class="indeterminate h-full w-1/3 rounded-full bg-accent" />
        </div>
      </div>
    </div>

    <div
      v-else-if="store.offline"
      class="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 p-6 text-center"
    >
      <Icon name="warning" :size="40" class="text-warn" />
      <div class="text-lg font-semibold">Cannot reach the server</div>
      <p class="max-w-sm text-sm text-ink-300">
        The API did not answer, so no models could be listed. Check that the backend is running, then try again.
      </p>
      <button class="btn" @click="store.init()"><Icon name="reset" /> Try again</button>
    </div>

    <div
      v-else-if="!store.currentId"
      class="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 p-6 text-center"
    >
      <Icon name="cube" :size="40" class="text-ink-500" />
      <div class="text-lg font-semibold">No model loaded</div>
      <p class="max-w-sm text-sm text-ink-300">
        Drop an <span class="font-mono text-ink-100">.ifc</span> file anywhere on this page, or use
        <span class="text-ink-100">Open IFC</span> in the header. Parsing happens on the server with IfcOpenShell.
      </p>
    </div>
  </section>
</template>

<style scoped>
.indeterminate {
  animation: slide 1.1s ease-in-out infinite;
}
@keyframes slide {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(300%);
  }
}
</style>
