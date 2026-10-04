<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatCarbon } from '../../lib/colors'
import type { DonutSegment } from './types'

const props = defineProps<{ segments: DonutSegment[]; activeKey?: string | null }>()
const emit = defineEmits<{ select: [segment: DonutSegment] }>()
const hovered = ref<string | null>(null)

const SIZE = 140
const R = 54
const STROKE = 18
const C = 2 * Math.PI * R

const total = computed(() => props.segments.reduce((sum, s) => sum + s.value, 0))
const arcs = computed(() => {
  let offset = 0
  return props.segments
    .filter((s) => s.value > 0)
    .map((s) => {
      const length = total.value ? (s.value / total.value) * C : 0
      const gap = Math.min(2, length * 0.25)
      const arc = { ...s, dash: `${Math.max(length - gap, 0.01)} ${C}`, offset: -offset }
      offset += length
      return arc
    })
})
const focused = computed(() => props.segments.find((s) => s.key === (hovered.value ?? props.activeKey)) ?? null)
</script>

<template>
  <svg :viewBox="`0 0 ${SIZE} ${SIZE}`" class="h-[140px] w-[140px] shrink-0" role="img" aria-label="Carbon by material">
    <g :transform="`rotate(-90 ${SIZE / 2} ${SIZE / 2})`">
      <circle :cx="SIZE / 2" :cy="SIZE / 2" :r="R" fill="none" stroke="var(--color-ink-700)" :stroke-width="STROKE" />
      <circle
        v-for="arc in arcs"
        :key="arc.key"
        :cx="SIZE / 2"
        :cy="SIZE / 2"
        :r="R"
        fill="none"
        :stroke="arc.color"
        :stroke-width="focused?.key === arc.key ? STROKE + 6 : STROKE"
        :stroke-dasharray="arc.dash"
        :stroke-dashoffset="arc.offset"
        class="cursor-pointer transition-[stroke-width,opacity] duration-150"
        :opacity="focused && focused.key !== arc.key ? 0.35 : 1"
        @pointerenter="hovered = arc.key"
        @pointerleave="hovered = null"
        @click="emit('select', arc)"
      >
        <title>{{ arc.label }}: {{ formatCarbon(arc.value) }}</title>
      </circle>
    </g>
    <text :x="SIZE / 2" :y="SIZE / 2 - 6" text-anchor="middle" class="fill-ink-300 text-[10px]">
      {{ focused ? focused.label : 'Total' }}
    </text>
    <text :x="SIZE / 2" :y="SIZE / 2 + 12" text-anchor="middle" class="fill-ink-100 font-mono text-[13px] font-semibold">
      {{ formatCarbon(focused ? focused.value : total) }}
    </text>
    <text v-if="focused && total" :x="SIZE / 2" :y="SIZE / 2 + 27" text-anchor="middle" class="fill-ink-300 text-[10px]">
      {{ ((focused.value / total) * 100).toFixed(1) }}%
    </text>
  </svg>
</template>
