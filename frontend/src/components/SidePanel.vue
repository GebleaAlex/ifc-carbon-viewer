<script setup lang="ts">
import { useViewerStore, type PanelTab } from '../stores/viewer'
import CarbonPanel from './CarbonPanel.vue'
import ElementsPanel from './ElementsPanel.vue'
import SelectionPanel from './SelectionPanel.vue'

const store = useViewerStore()
const tabs: { value: PanelTab; label: string }[] = [
  { value: 'carbon', label: 'Carbon' },
  { value: 'elements', label: 'Elements' },
  { value: 'selection', label: 'Selection' },
]
</script>

<template>
  <aside class="panel flex min-h-0 flex-col overflow-hidden">
    <nav class="flex border-b border-ink-700/80 text-sm" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        role="tab"
        class="flex-1 px-3 py-2.5 font-medium transition"
        :class="store.activeTab === tab.value ? 'border-b-2 border-accent text-ink-100' : 'text-ink-300 hover:text-ink-100'"
        :aria-selected="store.activeTab === tab.value"
        @click="store.activeTab = tab.value"
      >
        {{ tab.label }}
        <span v-if="tab.value === 'selection' && store.selectedId" class="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-accent" />
      </button>
    </nav>
    <div class="min-h-0 flex-1 overflow-auto p-3">
      <CarbonPanel v-if="store.activeTab === 'carbon'" />
      <ElementsPanel v-else-if="store.activeTab === 'elements'" />
      <SelectionPanel v-else />
    </div>
  </aside>
</template>
