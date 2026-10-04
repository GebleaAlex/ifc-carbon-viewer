import { computed, ref, shallowRef, watch } from 'vue'
import { defineStore } from 'pinia'
import { api, ApiError } from '../api/client'
import type {
  CarbonSummary,
  ElementDetail,
  ElementSummary,
  MaterialFactor,
  MaterialUsage,
  ModelSummary,
} from '../api/types'
import { carbonColor, classColor, materialColor, storeyColor, type ColorMode } from '../lib/colors'
import { matchesFocus, UNCLASSIFIED, type Focus } from '../lib/aggregate'

export type PanelTab = 'overview' | 'elements' | 'materials' | 'selection'

const COLOR_MODES: ColorMode[] = ['material', 'carbon', 'class', 'storey']

export const useViewerStore = defineStore('viewer', () => {
  // -- server data ----------------------------------------------------------------------
  const models = ref<ModelSummary[]>([])
  const factors = ref<MaterialFactor[]>([])
  const currentId = ref<string | null>(null)
  const elements = shallowRef<ElementSummary[]>([])
  const carbon = shallowRef<CarbonSummary | null>(null)
  const materials = shallowRef<MaterialUsage[]>([])
  const selectedDetail = shallowRef<ElementDetail | null>(null)

  // -- ui state -------------------------------------------------------------------------
  const colorMode = ref<ColorMode>('material')
  const hiddenStoreys = ref<Set<string>>(new Set())
  const hiddenClasses = ref<Set<string>>(new Set())
  const hiddenIds = ref<Set<string>>(new Set())
  const isolatedIds = ref<Set<string> | null>(null)
  const focus = ref<Focus | null>(null)
  const xray = ref(false)
  const sectionEnabled = ref(false)
  const sectionHeight = ref(0.6) // 0 = bottom of the model, 1 = top
  const selectedId = ref<string | null>(null)
  const hoveredId = ref<string | null>(null)
  const activeTab = ref<PanelTab>('overview')
  const loading = ref(false)
  const uploading = ref(false)
  const uploadProgress = ref<number | null>(null)
  const uploadName = ref<string | null>(null)
  const savingMapping = ref(false)
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)

  // -- derived --------------------------------------------------------------------------
  const currentModel = computed(() => models.value.find((m) => m.id === currentId.value) ?? null)
  const elementsById = computed(() => new Map(elements.value.map((e) => [e.global_id, e])))
  const factorColors = computed(() => Object.fromEntries(factors.value.map((f) => [f.category, f.color])))
  const factorLabels = computed<Record<string, string>>(() => ({
    ...Object.fromEntries(factors.value.map((f) => [f.category, f.label])),
    [UNCLASSIFIED]: 'Unclassified',
  }))
  const maxCarbon = computed(() => Math.max(0, ...elements.value.map((e) => e.carbon_kgco2e ?? 0)))
  const storeys = computed(() => currentModel.value?.storeys ?? [])
  const ifcClasses = computed(() => Object.keys(currentModel.value?.ifc_classes ?? {}))
  const hoveredElement = computed(() => (hoveredId.value ? (elementsById.value.get(hoveredId.value) ?? null) : null))
  const selectedElement = computed(() =>
    selectedId.value ? (elementsById.value.get(selectedId.value) ?? null) : null,
  )
  const overrides = computed<Record<string, string>>(() =>
    Object.fromEntries(materials.value.filter((m) => m.overridden).map((m) => [m.material, m.category ?? UNCLASSIFIED])),
  )
  const hiddenCount = computed(
    () =>
      hiddenStoreys.value.size +
      hiddenClasses.value.size +
      hiddenIds.value.size +
      (isolatedIds.value ? 1 : 0),
  )

  function isVisible(globalId: string): boolean {
    if (hiddenIds.value.has(globalId)) return false
    if (isolatedIds.value && !isolatedIds.value.has(globalId)) return false
    const element = elementsById.value.get(globalId)
    if (!element) return true
    if (hiddenClasses.value.has(element.ifc_class)) return false
    return !hiddenStoreys.value.has(element.storey ?? '')
  }

  /** Ghosted elements are drawn faintly and cannot be picked: outside the focus, or everything but the selection in X-ray. */
  function isGhosted(globalId: string): boolean {
    const element = elementsById.value.get(globalId)
    if (focus.value) return !element || !matchesFocus(element, focus.value)
    if (xray.value) return globalId !== selectedId.value
    return false
  }

  function colorFor(globalId: string): string | null {
    const element = elementsById.value.get(globalId)
    if (!element) return null
    switch (colorMode.value) {
      case 'carbon':
        return carbonColor(element.carbon_kgco2e, maxCarbon.value)
      case 'class':
        return classColor(element.ifc_class)
      case 'storey':
        return storeyColor(element.storey, storeys.value)
      default:
        return materialColor(element.material_category, factorColors.value)
    }
  }

  /** Glass reads as glass in the material view; the analytical views keep everything opaque. */
  function opacityFor(globalId: string): number {
    const element = elementsById.value.get(globalId)
    if (colorMode.value === 'material' && element?.material_category === 'glass') return 0.42
    return 1
  }

  // -- url state ------------------------------------------------------------------------
  function syncUrl(): void {
    const url = new URL(window.location.href)
    if (currentId.value) url.searchParams.set('model', currentId.value)
    else url.searchParams.delete('model')
    if (selectedId.value) url.searchParams.set('element', selectedId.value)
    else url.searchParams.delete('element')
    if (colorMode.value !== 'material') url.searchParams.set('color', colorMode.value)
    else url.searchParams.delete('color')
    window.history.replaceState(null, '', url)
  }
  watch(colorMode, syncUrl)

  // -- actions --------------------------------------------------------------------------
  async function init(): Promise<void> {
    try {
      const [modelList, factorList] = await Promise.all([api.listModels(), api.getFactors()])
      models.value = modelList
      factors.value = factorList
      const params = new URLSearchParams(window.location.search)
      const color = params.get('color') as ColorMode | null
      if (color && COLOR_MODES.includes(color)) colorMode.value = color
      const wanted = modelList.find((m) => m.id === params.get('model') && m.status === 'ready')
      const ready = wanted ?? modelList.find((m) => m.status === 'ready')
      if (ready) {
        await selectModel(ready.id)
        const element = params.get('element')
        if (wanted && element && elementsById.value.has(element)) await select(element)
        // Read-only view hints, handy for shared links and screenshots: ?tab=materials&section=0.55
        const tab = params.get('tab') as PanelTab | null
        if (tab && ['overview', 'elements', 'materials', 'selection'].includes(tab)) activeTab.value = tab
        const section = Number.parseFloat(params.get('section') ?? '')
        if (Number.isFinite(section)) {
          sectionHeight.value = Math.min(1, Math.max(0, section))
          sectionEnabled.value = true
        }
      }
      if (modelList.some((m) => m.status === 'processing')) void pollProcessing()
    } catch (e) {
      error.value = describe(e)
    }
  }

  /** Models re-parsed after an upgrade show up as "processing"; refresh the list until they are done. */
  async function pollProcessing(): Promise<void> {
    while (models.value.some((m) => m.status === 'processing')) {
      await sleep(1500)
      models.value = await api.listModels()
    }
    if (!currentId.value) {
      const ready = models.value.find((m) => m.status === 'ready')
      if (ready) await selectModel(ready.id)
    }
  }

  async function loadModelData(id: string): Promise<void> {
    const [elementList, carbonSummary, materialList] = await Promise.all([
      api.listElements(id),
      api.getCarbon(id),
      api.getMaterials(id),
    ])
    elements.value = elementList
    carbon.value = carbonSummary
    materials.value = materialList
  }

  async function selectModel(id: string): Promise<void> {
    if (currentId.value === id && elements.value.length) return
    loading.value = true
    error.value = null
    selectedId.value = null
    selectedDetail.value = null
    resetView()
    try {
      await loadModelData(id)
      currentId.value = id
      syncUrl()
    } catch (e) {
      error.value = describe(e)
    } finally {
      loading.value = false
    }
  }

  async function upload(file: File): Promise<void> {
    uploading.value = true
    uploadProgress.value = 0
    uploadName.value = file.name
    error.value = null
    try {
      let meta = await api.uploadModel(file, (fraction) => (uploadProgress.value = fraction))
      uploadProgress.value = null // now parsing on the server
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
      notice.value = `${meta.name} is ready: ${meta.element_count} elements in ${meta.parse_seconds}s`
    } catch (e) {
      error.value = describe(e)
    } finally {
      uploading.value = false
      uploadProgress.value = null
      uploadName.value = null
    }
  }

  async function removeModel(id: string): Promise<void> {
    await api.deleteModel(id)
    models.value = models.value.filter((m) => m.id !== id)
    if (currentId.value === id) {
      currentId.value = null
      elements.value = []
      carbon.value = null
      materials.value = []
      selectedId.value = null
      selectedDetail.value = null
      syncUrl()
      const next = models.value.find((m) => m.status === 'ready')
      if (next) await selectModel(next.id)
    }
  }

  async function select(globalId: string | null, openTab = true): Promise<void> {
    selectedId.value = globalId
    selectedDetail.value = null
    syncUrl()
    if (!globalId || !currentId.value) return
    if (openTab) activeTab.value = 'selection'
    try {
      selectedDetail.value = await api.getElement(currentId.value, globalId)
    } catch (e) {
      error.value = describe(e)
    }
  }

  /** Replace one material's category (or drop the override with `null`) and recompute on the server. */
  async function setMaterialCategory(material: string, category: string | null): Promise<void> {
    if (!currentId.value) return
    const next = { ...overrides.value }
    const row = materials.value.find((m) => m.material === material)
    if (category === null || (row && category === (row.auto_category ?? UNCLASSIFIED))) delete next[material]
    else next[material] = category
    await saveOverrides(next)
  }

  async function saveOverrides(next: Record<string, string>): Promise<void> {
    const id = currentId.value
    if (!id) return
    savingMapping.value = true
    try {
      const meta = await api.putMapping(id, { overrides: next })
      models.value = models.value.map((m) => (m.id === id ? meta : m))
      await loadModelData(id)
      if (selectedId.value) selectedDetail.value = await api.getElement(id, selectedId.value)
    } catch (e) {
      error.value = describe(e)
    } finally {
      savingMapping.value = false
    }
  }

  function toggleFocus(next: Focus): void {
    const same = focus.value?.kind === next.kind && focus.value.key === next.key
    focus.value = same ? null : next
  }

  function toggleStorey(storey: string): void {
    const next = new Set(hiddenStoreys.value)
    if (next.has(storey)) next.delete(storey)
    else next.add(storey)
    hiddenStoreys.value = next
  }

  function soloStorey(storey: string): void {
    const others = storeys.value.filter((s) => s !== storey)
    const alreadySolo = others.every((s) => hiddenStoreys.value.has(s)) && !hiddenStoreys.value.has(storey)
    hiddenStoreys.value = alreadySolo ? new Set() : new Set(others)
  }

  function toggleClass(ifcClass: string): void {
    const next = new Set(hiddenClasses.value)
    if (next.has(ifcClass)) next.delete(ifcClass)
    else next.add(ifcClass)
    hiddenClasses.value = next
  }

  function hideSelected(): void {
    if (!selectedId.value) return
    hiddenIds.value = new Set([...hiddenIds.value, selectedId.value])
    void select(null, false)
  }

  function isolateSelected(): void {
    if (!selectedId.value) return
    const element = elementsById.value.get(selectedId.value)
    const ids = new Set([selectedId.value])
    // Isolating a part of an assembly keeps its siblings out; isolating an assembly keeps its parts in.
    if (element?.is_assembly && selectedDetail.value) selectedDetail.value.part_global_ids.forEach((p) => ids.add(p))
    isolatedIds.value = ids
  }

  function showAll(): void {
    hiddenStoreys.value = new Set()
    hiddenClasses.value = new Set()
    hiddenIds.value = new Set()
    isolatedIds.value = null
  }

  function resetView(): void {
    showAll()
    focus.value = null
    xray.value = false
    sectionEnabled.value = false
  }

  return {
    models,
    factors,
    currentId,
    currentModel,
    elements,
    elementsById,
    carbon,
    materials,
    selectedDetail,
    colorMode,
    hiddenStoreys,
    hiddenClasses,
    hiddenIds,
    isolatedIds,
    hiddenCount,
    focus,
    xray,
    sectionEnabled,
    sectionHeight,
    selectedId,
    hoveredId,
    hoveredElement,
    selectedElement,
    activeTab,
    loading,
    uploading,
    uploadProgress,
    uploadName,
    savingMapping,
    error,
    notice,
    factorColors,
    factorLabels,
    maxCarbon,
    storeys,
    ifcClasses,
    overrides,
    isVisible,
    isGhosted,
    colorFor,
    opacityFor,
    init,
    selectModel,
    upload,
    removeModel,
    select,
    setMaterialCategory,
    saveOverrides,
    toggleFocus,
    toggleStorey,
    soloStorey,
    toggleClass,
    hideSelected,
    isolateSelected,
    showAll,
    resetView,
  }
})

function describe(e: unknown): string {
  if (e instanceof ApiError) return e.status ? `${e.status}: ${e.message}` : e.message
  if (e instanceof Error) return e.message
  return String(e)
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
