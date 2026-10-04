<script setup lang="ts" generic="T extends string | number">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './Icon.vue'
import type { SelectOption } from './types'

// A themed dropdown: the native <select> popup ignores the dark theme and cannot show colours or sublines.
// The menu is teleported to <body> so scrolling panels never clip it.

const props = withDefaults(
  defineProps<{
    modelValue: T | null
    options: SelectOption<T>[]
    placeholder?: string
    label: string
    size?: 'sm' | 'md'
    searchable?: boolean
    minWidth?: number
    disabled?: boolean
  }>(),
  { placeholder: 'Choose…', size: 'md', searchable: undefined, minWidth: 220, disabled: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: T]; change: [value: T] }>()

const open = ref(false)
const query = ref('')
const active = ref(0)
const trigger = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLDivElement | null>(null)
const search = ref<HTMLInputElement | null>(null)
const position = ref({ top: 0, left: 0, width: 0, up: false })

const current = computed(() => props.options.find((o) => o.value === props.modelValue) ?? null)
const showSearch = computed(() => props.searchable ?? props.options.length > 8)
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter((o) => `${o.label} ${o.sub ?? ''}`.toLowerCase().includes(q))
})

function place() {
  const rect = trigger.value?.getBoundingClientRect()
  if (!rect) return
  const width = Math.max(rect.width, props.minWidth)
  const spaceBelow = window.innerHeight - rect.bottom
  const up = spaceBelow < 280 && rect.top > spaceBelow
  const left = Math.min(rect.left, window.innerWidth - width - 8)
  position.value = { top: up ? rect.top - 6 : rect.bottom + 6, left: Math.max(8, left), width, up }
}

async function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (!open.value) return
  query.value = ''
  place()
  active.value = Math.max(0, filtered.value.findIndex((o) => o.value === props.modelValue))
  await nextTick()
  if (showSearch.value) search.value?.focus()
  else menu.value?.focus()
  scrollActiveIntoView()
}

function choose(option: SelectOption<T>) {
  if (option.disabled) return
  open.value = false
  if (option.value !== props.modelValue) {
    emit('update:modelValue', option.value)
    emit('change', option.value)
  }
  trigger.value?.focus()
}

function scrollActiveIntoView() {
  nextTick(() => menu.value?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' }))
}

function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    open.value = false
    trigger.value?.focus()
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const step = event.key === 'ArrowDown' ? 1 : -1
    const count = filtered.value.length
    if (!count) return
    let next = active.value
    for (let i = 0; i < count; i++) {
      next = (next + step + count) % count
      if (!filtered.value[next]?.disabled) break
    }
    active.value = next
    scrollActiveIntoView()
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const option = filtered.value[active.value]
    if (option) choose(option)
  } else if (event.key === 'Tab') {
    open.value = false
  }
}

function onOutside(event: PointerEvent) {
  const target = event.target as Node
  if (!menu.value?.contains(target) && !trigger.value?.contains(target)) open.value = false
}

watch(open, (isOpen) => {
  if (isOpen) {
    window.addEventListener('pointerdown', onOutside, true)
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
  } else {
    window.removeEventListener('pointerdown', onOutside, true)
    window.removeEventListener('resize', place)
    window.removeEventListener('scroll', place, true)
  }
})
watch(query, () => (active.value = 0))
onBeforeUnmount(() => (open.value = false))
</script>

<template>
  <button
    ref="trigger"
    type="button"
    class="ui-select-trigger"
    :class="[size === 'sm' ? 'h-7 px-2 text-xs' : 'h-9 px-3 text-sm', { 'is-open': open }]"
    :aria-label="label"
    aria-haspopup="listbox"
    :aria-expanded="open"
    :disabled="disabled"
    @click="toggle"
    @keydown.down.prevent="!open && toggle()"
  >
    <span v-if="current?.color" class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: current.color }" />
    <span class="min-w-0 flex-1 truncate text-left" :class="current ? 'text-ink-100' : 'text-ink-300'">
      <slot name="current" :option="current">{{ current?.label ?? placeholder }}</slot>
    </span>
    <Icon name="chevron" :size="14" class="text-ink-300 transition" :class="{ 'rotate-180': open }" />
  </button>

  <Teleport to="body">
    <Transition name="pop">
      <div
        v-if="open"
        ref="menu"
        class="ui-select-menu"
        :style="{
          top: `${position.top}px`,
          left: `${position.left}px`,
          width: `${position.width}px`,
          transform: position.up ? 'translateY(-100%)' : undefined,
        }"
        role="listbox"
        :aria-label="label"
        tabindex="-1"
        @keydown="onKey"
      >
        <div v-if="showSearch" class="border-b border-ink-700 p-1.5">
          <div class="flex items-center gap-2 rounded-md bg-ink-900 px-2">
            <Icon name="search" :size="14" class="text-ink-300" />
            <input
              ref="search"
              v-model="query"
              class="h-8 w-full bg-transparent text-sm outline-none placeholder:text-ink-500"
              :placeholder="`Search ${label.toLowerCase()}…`"
            />
          </div>
        </div>
        <ul class="max-h-72 overflow-auto p-1">
          <li
            v-for="(option, i) in filtered"
            :key="String(option.value)"
            role="option"
            :aria-selected="option.value === modelValue"
            :aria-disabled="option.disabled"
            :data-active="i === active"
            class="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm"
            :class="[
              i === active ? 'bg-ink-700 text-ink-100' : 'text-ink-200',
              option.disabled ? 'cursor-not-allowed opacity-45' : '',
            ]"
            @pointerenter="active = i"
            @click="choose(option)"
          >
            <span v-if="option.color" class="h-2.5 w-2.5 shrink-0 rounded-sm" :style="{ background: option.color }" />
            <span class="min-w-0 flex-1">
              <span class="block truncate">{{ option.label }}</span>
              <span v-if="option.sub" class="block truncate text-[11px] text-ink-300">{{ option.sub }}</span>
            </span>
            <Icon v-if="option.value === modelValue" name="check" :size="14" class="text-accent" />
          </li>
          <li v-if="!filtered.length" class="px-2.5 py-3 text-center text-xs text-ink-300">Nothing matches</li>
        </ul>
      </div>
    </Transition>
  </Teleport>
</template>
