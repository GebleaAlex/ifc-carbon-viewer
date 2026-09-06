<script setup lang="ts">
import { ref } from 'vue'
import { useViewerStore } from '../stores/viewer'
import type { ColorMode } from '../lib/colors'

const emit = defineEmits<{ fit: []; 'fit-selection': [] }>()
const store = useViewerStore()
const classesOpen = ref(false)

const modes: { value: ColorMode; label: string; hint: string }[] = [
  { value: 'material', label: 'Material', hint: 'Colour by classified material' },
  { value: 'carbon', label: 'Carbon', hint: 'Colour by embodied carbon' },
  { value: 'class', label: 'IFC class', hint: 'Colour by IFC entity type' },
]
</script>

<template>
  <div class="flex flex-wrap items-start gap-2">
    <div class="seg" role="group" aria-label="Colour mode">
      <button
        v-for="mode in modes"
        :key="mode.value"
        :aria-pressed="store.colorMode === mode.value"
        :title="mode.hint"
        @click="store.colorMode = mode.value"
      >
        {{ mode.label }}
      </button>
    </div>

    <div v-if="store.storeys.length" class="seg" role="group" aria-label="Storeys">
      <button
        v-for="storey in store.storeys"
        :key="storey"
        :aria-pressed="!store.hiddenStoreys.has(storey)"
        :title="`Toggle ${storey}`"
        @click="store.toggleStorey(storey)"
      >
        {{ storey }}
      </button>
    </div>

    <div v-if="store.ifcClasses.length" class="relative">
      <button class="btn py-1 text-xs" :aria-expanded="classesOpen" @click="classesOpen = !classesOpen">
        Classes
        <span v-if="store.hiddenClasses.size" class="rounded bg-warn/20 px-1 text-warn">{{ store.hiddenClasses.size }} hidden</span>
      </button>
      <div
        v-if="classesOpen"
        class="panel absolute left-0 top-full z-20 mt-1 max-h-72 w-60 overflow-auto p-2 text-xs shadow-xl"
      >
        <label
          v-for="ifcClass in store.ifcClasses"
          :key="ifcClass"
          class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-ink-700"
        >
          <input
            type="checkbox"
            class="accent-accent"
            :checked="!store.hiddenClasses.has(ifcClass)"
            @change="store.toggleClass(ifcClass)"
          />
          <span class="flex-1 truncate">{{ ifcClass }}</span>
          <span class="text-ink-300">{{ store.currentModel?.ifc_classes[ifcClass] }}</span>
        </label>
        <button class="mt-1 w-full rounded px-2 py-1 text-left text-ink-300 hover:bg-ink-700" @click="store.showAll()">
          Show everything
        </button>
      </div>
    </div>

    <button class="btn py-1 text-xs" title="Fit the whole model" @click="emit('fit')">Fit</button>
    <button
      v-if="store.selectedId"
      class="btn py-1 text-xs"
      title="Fit the selected element"
      @click="emit('fit-selection')"
    >
      Fit selection
    </button>
  </div>
</template>
