<script setup lang="ts">
import { computed, nextTick } from 'vue'
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

/** Arrow keys, Home and End move between tabs, as the tablist pattern expects. */
function onTabKey(event: KeyboardEvent) {
  const index = tabs.findIndex((t) => t.value === store.activeTab)
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabs.length - 1
  else return
  event.preventDefault()
  store.activeTab = tabs[next]!.value
  const list = event.currentTarget as HTMLElement
  void nextTick(() => list.querySelector<HTMLElement>('[aria-selected="true"]')?.focus())
}
</script>

<template>
  <aside class="panel flex flex-col lg:min-h-0 lg:overflow-hidden">
    <nav class="flex border-b border-ink-700/80 px-1 text-sm" role="tablist" aria-label="Model details" @keydown="onTabKey">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        :id="`tab-${tab.value}`"
        role="tab"
        aria-controls="side-panel-body"
        :tabindex="store.activeTab === tab.value ? 0 : -1"
        class="relative flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap px-1.5 py-2.5 font-medium transition sm:px-2"
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
    <div id="side-panel-body" role="tabpanel" :aria-labelledby="`tab-${store.activeTab}`" class="p-3 lg:min-h-0 lg:flex-1 lg:overflow-auto">
      <OverviewPanel v-if="store.activeTab === 'overview'" />
      <ElementsPanel v-else-if="store.activeTab === 'elements'" />
      <MaterialsPanel v-else-if="store.activeTab === 'materials'" />
      <SelectionPanel v-else />
    </div>
  </aside>
</template>
