import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { api, ApiError } from '../api/client'
import type { CarbonSummary, ElementDetail, ElementSummary, MaterialFactor, ModelSummary } from '../api/types'
import { carbonColor, classColor, materialColor, type ColorMode } from '../lib/colors'

export type PanelTab = 'carbon' | 'elements' | 'selection'

export const useViewerStore = defineStore('viewer', () => {
  // -- server data ----------------------------------------------------------------------
  const models = ref<ModelSummary[]>([])
  const factors = ref<MaterialFactor[]>([])
  const currentId = ref<string | null>(null)
  const elements = shallowRef<ElementSummary[]>([])
  const carbon = shallowRef<CarbonSummary | null>(null)
  const selectedDetail = shallowRef<ElementDetail | null>(null)

  // -- ui state -------------------------------------------------------------------------
  const colorMode = ref<ColorMode>('material')
  const hiddenStoreys = ref<Set<string>>(new Set())
  const hiddenClasses = ref<Set<string>>(new Set())
  const selectedId = ref<string | null>(null)
  const hoveredId = ref<string | null>(null)
  const activeTab = ref<PanelTab>('carbon')
  const loading = ref(false)
  const uploading = ref(false)
  const error = ref<string | null>(null)

  // -- derived --------------------------------------------------------------------------
  const currentModel = computed(() => models.value.find((m) => m.id === currentId.value) ?? null)
  const elementsById = computed(() => new Map(elements.value.map((e) => [e.global_id, e])))
  const factorColors = computed(() => Object.fromEntries(factors.value.map((f) => [f.category, f.color])))
  const factorLabels = computed(() => Object.fromEntries(factors.value.map((f) => [f.category, f.label])))
  const maxCarbon = computed(() => Math.max(0, ...elements.value.map((e) => e.carbon_kgco2e ?? 0)))
  const storeys = computed(() => currentModel.value?.storeys ?? [])
  const ifcClasses = computed(() => Object.keys(currentModel.value?.ifc_classes ?? {}))
  const hoveredElement = computed(() => (hoveredId.value ? elementsById.value.get(hoveredId.value) ?? null : null))
  const selectedElement = computed(() => (selectedId.value ? elementsById.value.get(selectedId.value) ?? null : null))

  function isVisible(globalId: string): boolean {
    const element = elementsById.value.get(globalId)
    if (!element) return true
    if (hiddenClasses.value.has(element.ifc_class)) return false
    return !hiddenStoreys.value.has(element.storey ?? '')
  }

  function colorFor(globalId: string): string | null {
    const element = elementsById.value.get(globalId)
    if (!element) return null
    switch (colorMode.value) {
      case 'carbon':
        return carbonColor(element.carbon_kgco2e, maxCarbon.value)
      case 'class':
        return classColor(element.ifc_class)
      default:
        return materialColor(element.material_category, factorColors.value)
    }
  }

  // -- actions --------------------------------------------------------------------------
  async function init(): Promise<void> {
    try {
      const [modelList, factorList] = await Promise.all([api.listModels(), api.getFactors()])
      models.value = modelList
      factors.value = factorList
      const ready = modelList.find((m) => m.status === 'ready')
      if (ready) await selectModel(ready.id)
    } catch (e) {
      error.value = describe(e)
    }
  }

  async function refreshModels(): Promise<void> {
    models.value = await api.listModels()
  }

  async function selectModel(id: string): Promise<void> {
    if (currentId.value === id && elements.value.length) return
    loading.value = true
    error.value = null
    selectedId.value = null
    selectedDetail.value = null
    hiddenStoreys.value = new Set()
    hiddenClasses.value = new Set()
    try {
      const [elementList, carbonSummary] = await Promise.all([api.listElements(id), api.getCarbon(id)])
      elements.value = elementList
      carbon.value = carbonSummary
      currentId.value = id
    } catch (e) {
      error.value = describe(e)
    } finally {
      loading.value = false
    }
  }

  async function upload(file: File): Promise<void> {
    uploading.value = true
    error.value = null
    try {
      let meta = await api.uploadModel(file)
      models.value = [meta, ...models.value]
      while (meta.status === 'processing') {
        await sleep(800)
        meta = await api.getModel(meta.id)
        models.value = models.value.map((m) => (m.id === meta.id ? meta : m))
      }
      if (meta.status === 'failed') {
        error.value = meta.error ?? 'The model could not be parsed.'
        return
      }
      await selectModel(meta.id)
    } catch (e) {
      error.value = describe(e)
    } finally {
      uploading.value = false
    }
  }

  async function removeModel(id: string): Promise<void> {
    await api.deleteModel(id)
    models.value = models.value.filter((m) => m.id !== id)
    if (currentId.value === id) {
      currentId.value = null
      elements.value = []
      carbon.value = null
      selectedId.value = null
      const next = models.value.find((m) => m.status === 'ready')
      if (next) await selectModel(next.id)
    }
  }

  async function select(globalId: string | null): Promise<void> {
    selectedId.value = globalId
    selectedDetail.value = null
    if (!globalId || !currentId.value) return
    activeTab.value = 'selection'
    try {
      selectedDetail.value = await api.getElement(currentId.value, globalId)
    } catch (e) {
      error.value = describe(e)
    }
  }

  function toggleStorey(storey: string): void {
    const next = new Set(hiddenStoreys.value)
    if (next.has(storey)) next.delete(storey)
    else next.add(storey)
    hiddenStoreys.value = next
  }

  function toggleClass(ifcClass: string): void {
    const next = new Set(hiddenClasses.value)
    if (next.has(ifcClass)) next.delete(ifcClass)
    else next.add(ifcClass)
    hiddenClasses.value = next
  }

  function showAll(): void {
    hiddenStoreys.value = new Set()
    hiddenClasses.value = new Set()
  }

  return {
    models,
    factors,
    currentId,
    currentModel,
    elements,
    elementsById,
    carbon,
    selectedDetail,
    colorMode,
    hiddenStoreys,
    hiddenClasses,
    selectedId,
    hoveredId,
    hoveredElement,
    selectedElement,
    activeTab,
    loading,
    uploading,
    error,
    factorColors,
    factorLabels,
    maxCarbon,
    storeys,
    ifcClasses,
    isVisible,
    colorFor,
    init,
    refreshModels,
    selectModel,
    upload,
    removeModel,
    select,
    toggleStorey,
    toggleClass,
    showAll,
  }
})

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`
  if (e instanceof Error) return e.message
  return String(e)
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
