<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useViewerStore } from './stores/viewer'
import { viewerBridge } from './lib/viewerBridge'
import type { ColorMode } from './lib/colors'
import TopBar from './components/TopBar.vue'
import ViewerPanel from './components/ViewerPanel.vue'
import SidePanel from './components/SidePanel.vue'
import UploadDropzone from './components/UploadDropzone.vue'
import ConfirmDialog from './components/ui/ConfirmDialog.vue'
import Icon from './components/ui/Icon.vue'

const store = useViewerStore()
const helpOpen = ref(false)

const SHORTCUTS: [string, string][] = [
  ['F', 'Fit the model'],
  ['Z', 'Zoom to the selection'],
  ['I', 'Isolate the selection'],
  ['H', 'Hide the selection'],
  ['Shift H', 'Show everything'],
  ['X', 'X-ray'],
  ['S', 'Section cut'],
  ['1 – 4', 'Colour by material, carbon, class, storey'],
  ['Esc', 'Clear focus, then selection'],
  ['?', 'This list'],
]
const MODES: ColorMode[] = ['material', 'carbon', 'class', 'storey']

function onKey(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return
  if (event.ctrlKey || event.metaKey || event.altKey) return
  const key = event.key.toLowerCase()
  if (key === 'escape') {
    if (helpOpen.value) helpOpen.value = false
    else if (store.focus) store.focus = null
    else if (store.selectedId) void store.select(null, false)
    else if (store.isolatedIds) store.isolatedIds = null
    return
  }
  if (event.key === '?') helpOpen.value = !helpOpen.value
  else if (key === 'f') viewerBridge.fit()
  else if (key === 'z' && store.selectedId) viewerBridge.fit([store.selectedId])
  else if (key === 'i') store.isolateSelected()
  else if (key === 'h' && event.shiftKey) store.showAll()
  else if (key === 'h') store.hideSelected()
  else if (key === 'x') store.xray = !store.xray
  else if (key === 's') store.sectionEnabled = !store.sectionEnabled
  else if (['1', '2', '3', '4'].includes(key)) store.colorMode = MODES[Number(key) - 1]!
  else return
  event.preventDefault()
}

let noticeTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => store.notice,
  (notice) => {
    clearTimeout(noticeTimer)
    if (notice) noticeTimer = setTimeout(() => (store.notice = null), 3500)
  },
)

onMounted(() => {
  store.init()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="flex h-full flex-col">
    <TopBar @help="helpOpen = true" />
    <main
      class="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(420px,62vh)_auto] gap-3 overflow-auto p-3 lg:grid-cols-[minmax(0,1fr)_400px] lg:grid-rows-1 lg:overflow-hidden"
    >
      <ViewerPanel />
      <SidePanel class="lg:min-h-0" />
    </main>
    <UploadDropzone />
    <ConfirmDialog />

    <!-- toasts -->
    <div class="pointer-events-none fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2">
      <Transition name="fade">
        <div
          v-if="store.error"
          class="pointer-events-auto flex max-w-[90vw] items-center gap-3 rounded-lg border border-bad/40 bg-ink-800 px-4 py-2 text-sm text-ink-100 shadow-xl"
          role="alert"
        >
          <Icon name="warning" class="text-bad" />
          <span>{{ store.error }}</span>
          <button class="text-ink-300 hover:text-ink-100" aria-label="Dismiss" @click="store.error = null"><Icon name="close" :size="14" /></button>
        </div>
      </Transition>
      <Transition name="fade">
        <div
          v-if="store.notice"
          class="flex max-w-[90vw] items-center gap-2 rounded-lg border border-good/40 bg-ink-800 px-4 py-2 text-sm text-ink-100 shadow-xl"
          role="status"
        >
          <Icon name="check" class="text-good" /> {{ store.notice }}
        </div>
      </Transition>
    </div>

    <!-- keyboard shortcuts -->
    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="helpOpen"
          class="fixed inset-0 z-[60] flex items-center justify-center bg-ink-950/70 p-4 backdrop-blur-sm"
          @click.self="helpOpen = false"
        >
          <div class="panel w-full max-w-sm p-5 shadow-2xl" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
            <div class="mb-3 flex items-center justify-between">
              <h2 class="text-base font-semibold">Keyboard shortcuts</h2>
              <button class="tool" aria-label="Close" @click="helpOpen = false"><Icon name="close" /></button>
            </div>
            <dl class="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
              <template v-for="[keys, label] in SHORTCUTS" :key="keys">
                <dt><span class="kbd">{{ keys }}</span></dt>
                <dd class="text-ink-200">{{ label }}</dd>
              </template>
            </dl>
            <p class="mt-4 text-xs text-ink-500">Drag to orbit · right-drag to pan · scroll to zoom · click to select</p>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
