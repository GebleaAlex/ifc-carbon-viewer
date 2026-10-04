<script setup lang="ts">
import { computed } from 'vue'
import { useViewerStore, type PanelTab } from '../stores/viewer'
import OverviewPanel from './OverviewPanel.vue'
import ElementsPanel from './ElementsPanel.vue'
import MaterialsPanel from './MaterialsPanel.vue'
import SelectionPanel from './SelectionPanel.vue'

const store = useViewerStore()
const unclassified = computed(() => store.materials.filter((m) => !m.category).length)
const tabs: { value: PanelTab; label: string }[] = [
  { value: 'overview', label: 'Overview' },
  { value: 'elements', label: 'Elements' },
  { value: 'materials', label: 'Materials' },
  { value: 'selection', label: 'Selection' },
]
</script>

<template>
  <aside class="panel flex flex-col lg:min-h-0 lg:overflow-hidden">
    <nav class="flex border-b border-ink-700/80 px-1 text-sm" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        role="tab"
        class="relative flex flex-1 items-center justify-center gap-1.5 px-2 py-2.5 font-medium transition"
        :class="store.activeTab === tab.value ? 'text-ink-100' : 'text-ink-300 hover:text-ink-100'"
        :aria-selected="store.activeTab === tab.value"
        @click="store.activeTab = tab.value"
      >
        {{ tab.label }}
        <span
          v-if="tab.value === 'materials' && unclassified"
          class="rounded-full bg-warn/20 px-1.5 text-[10px] font-semibold text-warn"
          :title="`${unclassified} unclassified`"
        >
          {{ unclassified }}
        </span>
        <span v-if="tab.value === 'selection' && store.selectedId" class="h-1.5 w-1.5 rounded-full bg-accent" />
        <span
          v-if="store.activeTab === tab.value"
          class="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent"
        />
      </button>
    </nav>
    <div class="p-3 lg:min-h-0 lg:flex-1 lg:overflow-auto">
      <OverviewPanel v-if="store.activeTab === 'overview'" />
      <ElementsPanel v-else-if="store.activeTab === 'elements'" />
      <MaterialsPanel v-else-if="store.activeTab === 'materials'" />
      <SelectionPanel v-else />
    </div>
  </aside>
</template>
