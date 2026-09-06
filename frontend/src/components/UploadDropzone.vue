<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useViewerStore } from '../stores/viewer'

const store = useViewerStore()
const dragging = ref(false)
let depth = 0

function hasFiles(event: DragEvent) {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

function onDragEnter(event: DragEvent) {
  if (!hasFiles(event)) return
  depth++
  dragging.value = true
}

function onDragLeave() {
  depth = Math.max(0, depth - 1)
  if (depth === 0) dragging.value = false
}

function onDragOver(event: DragEvent) {
  if (hasFiles(event)) event.preventDefault()
}

function onDrop(event: DragEvent) {
  event.preventDefault()
  depth = 0
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.ifc')) {
    store.error = 'Only .ifc files are supported.'
    return
  }
  store.upload(file)
}

onMounted(() => {
  window.addEventListener('dragenter', onDragEnter)
  window.addEventListener('dragleave', onDragLeave)
  window.addEventListener('dragover', onDragOver)
  window.addEventListener('drop', onDrop)
})

onBeforeUnmount(() => {
  window.removeEventListener('dragenter', onDragEnter)
  window.removeEventListener('dragleave', onDragLeave)
  window.removeEventListener('dragover', onDragOver)
  window.removeEventListener('drop', onDrop)
})
</script>

<template>
  <div
    v-if="dragging"
    class="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-ink-950/70 backdrop-blur-sm"
  >
    <div class="rounded-2xl border-2 border-dashed border-accent px-10 py-8 text-center">
      <div class="text-lg font-semibold">Drop the IFC file to open it</div>
      <div class="mt-1 text-sm text-ink-300">IFC2X3, IFC4 and IFC4X3 are supported</div>
    </div>
  </div>
</template>
