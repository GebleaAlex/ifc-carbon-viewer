<script setup lang="ts">
import { onMounted } from 'vue'
import { useViewerStore } from './stores/viewer'
import TopBar from './components/TopBar.vue'
import ViewerPanel from './components/ViewerPanel.vue'
import SidePanel from './components/SidePanel.vue'
import UploadDropzone from './components/UploadDropzone.vue'

const store = useViewerStore()
onMounted(() => store.init())
</script>

<template>
  <div class="flex h-full flex-col">
    <TopBar />
    <main class="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_380px]">
      <ViewerPanel />
      <SidePanel />
    </main>
    <UploadDropzone />
    <transition name="fade">
      <div
        v-if="store.error"
        class="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-bad/40 bg-ink-800 px-4 py-2 text-sm text-ink-100 shadow-xl"
        role="alert"
      >
        <span class="mr-3 font-medium text-bad">Error</span>{{ store.error }}
        <button class="ml-4 text-ink-300 hover:text-ink-100" @click="store.error = null" aria-label="Dismiss">✕</button>
      </div>
    </transition>
  </div>
</template>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
