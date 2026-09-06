<script setup lang="ts">
import type { CarbonBucket } from '../api/types'
import { formatCarbon } from '../lib/colors'

defineProps<{
  title: string
  buckets: CarbonBucket[]
  colorFor?: (bucket: CarbonBucket) => string
}>()
</script>

<template>
  <section>
    <h3 class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-300">{{ title }}</h3>
    <ul class="space-y-1.5">
      <li v-for="bucket in buckets" :key="bucket.key" class="text-xs">
        <div class="flex items-baseline justify-between gap-2">
          <span class="flex items-center gap-2 truncate text-ink-100">
            <span
              v-if="colorFor"
              class="inline-block h-2 w-2 shrink-0 rounded-sm"
              :style="{ background: colorFor(bucket) }"
            />
            <span class="truncate">{{ bucket.label }}</span>
            <span class="text-ink-500">{{ bucket.element_count }}</span>
          </span>
          <span class="shrink-0 font-mono text-ink-200">
            {{ formatCarbon(bucket.carbon_kgco2e) }}
            <span class="ml-1 text-ink-500">{{ bucket.share_percent }}%</span>
          </span>
        </div>
        <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-700">
          <div
            class="h-full rounded-full transition-all"
            :style="{ width: `${Math.max(bucket.share_percent, 1)}%`, background: colorFor ? colorFor(bucket) : '#38bdf8' }"
          />
        </div>
      </li>
    </ul>
  </section>
</template>
