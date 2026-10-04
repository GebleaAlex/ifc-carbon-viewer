<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CarbonBucket } from '../api/types'
import { formatCarbon } from '../lib/colors'

const props = withDefaults(
  defineProps<{
    title: string
    buckets: CarbonBucket[]
    colorFor?: (bucket: CarbonBucket) => string
    activeKey?: string | null
    limit?: number
  }>(),
  { activeKey: null, limit: 8, colorFor: undefined },
)
const emit = defineEmits<{ select: [bucket: CarbonBucket] }>()
const expanded = ref(false)
const shown = computed(() => (expanded.value ? props.buckets : props.buckets.slice(0, props.limit)))
const max = computed(() => Math.max(...props.buckets.map((b) => b.carbon_kgco2e), 1))
</script>

<template>
  <section>
    <h3 class="section-title mb-2">{{ title }}</h3>
    <ul class="space-y-0.5">
      <li v-for="bucket in shown" :key="bucket.key">
        <button
          class="w-full rounded-md px-1.5 py-1 text-left text-xs transition hover:bg-ink-700/60"
          :class="activeKey === bucket.key ? 'bg-accent/10 ring-1 ring-accent/40' : ''"
          :title="`Show only ${bucket.label} in the 3D view`"
          @click="emit('select', bucket)"
        >
          <div class="flex items-baseline justify-between gap-2">
            <span class="flex min-w-0 items-center gap-2 text-ink-100">
              <span v-if="colorFor" class="inline-block h-2 w-2 shrink-0 rounded-sm" :style="{ background: colorFor(bucket) }" />
              <span class="truncate">{{ bucket.label }}</span>
              <span class="shrink-0 text-ink-500">{{ bucket.element_count }}</span>
            </span>
            <span class="shrink-0 font-mono text-ink-200">
              {{ formatCarbon(bucket.carbon_kgco2e) }}
              <span class="ml-1 inline-block w-10 text-right text-ink-500">{{ bucket.share_percent }}%</span>
            </span>
          </div>
          <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-700">
            <div
              class="h-full rounded-full transition-all"
              :style="{
                width: `${Math.max((bucket.carbon_kgco2e / max) * 100, 1)}%`,
                background: colorFor ? colorFor(bucket) : '#38bdf8',
              }"
            />
          </div>
        </button>
      </li>
    </ul>
    <button
      v-if="buckets.length > limit"
      class="mt-1 px-1.5 text-[11px] font-medium text-accent hover:underline"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'Show fewer' : `Show all ${buckets.length}` }}
    </button>
  </section>
</template>
