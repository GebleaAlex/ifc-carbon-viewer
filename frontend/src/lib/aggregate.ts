/** Client-side aggregations over the element list: focus matching and the storey x material matrix. */
import type { ElementSummary } from '../api/types'

export const UNCLASSIFIED = 'unclassified'

export type FocusKind = 'material' | 'storey' | 'class' | 'quality'
export type QualityIssue = 'unclassified' | 'partial' | 'no-volume'

export interface Focus {
  kind: FocusKind
  key: string
  label: string
}

/** Categories an element contributes to: one per layer that has volume, or its own category. */
export function categoriesOf(element: ElementSummary): string[] {
  const fromLayers = element.layers.filter((l) => l.volume_m3).map((l) => l.category ?? UNCLASSIFIED)
  if (fromLayers.length) return [...new Set(fromLayers)]
  return [element.material_category ?? UNCLASSIFIED]
}

export function hasIssue(element: ElementSummary, issue: QualityIssue): boolean {
  if (element.is_assembly) return false
  if (issue === 'unclassified') return element.material_category === null
  if (issue === 'partial') return element.partially_classified
  return element.volume_m3 === null
}

export function matchesFocus(element: ElementSummary, focus: Focus | null): boolean {
  if (!focus) return true
  switch (focus.kind) {
    case 'material':
      return categoriesOf(element).includes(focus.key)
    case 'storey':
      return (element.storey ?? 'No storey') === focus.key
    case 'class':
      return element.ifc_class === focus.key
    case 'quality':
      return hasIssue(element, focus.key as QualityIssue)
  }
}

export interface StoreyStack {
  storey: string
  total: number
  segments: { category: string; carbon: number }[]
}

/** Carbon per storey split by material category, storeys in the given (elevation) order. */
export function storeyMaterialStacks(elements: ElementSummary[], storeys: string[]): StoreyStack[] {
  const table = new Map<string, Map<string, number>>()
  for (const element of elements) {
    if (element.is_assembly) continue
    const storey = element.storey ?? 'No storey'
    const row = table.get(storey) ?? new Map<string, number>()
    table.set(storey, row)
    const layers = element.layers.filter((l) => l.carbon_kgco2e)
    if (layers.length) {
      for (const layer of layers) {
        const key = layer.category ?? UNCLASSIFIED
        row.set(key, (row.get(key) ?? 0) + (layer.carbon_kgco2e ?? 0))
      }
    } else if (element.carbon_kgco2e) {
      const key = element.material_category ?? UNCLASSIFIED
      row.set(key, (row.get(key) ?? 0) + element.carbon_kgco2e)
    }
  }
  const order = [...storeys, ...[...table.keys()].filter((s) => !storeys.includes(s))]
  return order
    .filter((storey) => table.has(storey))
    .map((storey) => {
      const segments = [...table.get(storey)!.entries()]
        .map(([category, carbon]) => ({ category, carbon }))
        .filter((s) => s.carbon > 0)
        .sort((a, b) => b.carbon - a.carbon)
      return { storey, total: segments.reduce((sum, s) => sum + s.carbon, 0), segments }
    })
}
