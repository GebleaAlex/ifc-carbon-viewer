import { describe, expect, it } from 'vitest'
import type { ElementSummary, MaterialLayer } from '../api/types'
import { categoriesOf, hasIssue, matchesFocus, storeyMaterialStacks } from './aggregate'

function layer(material: string, category: string | null, volume: number | null, carbon: number | null): MaterialLayer {
  return { material, category, volume_m3: volume, carbon_kgco2e: carbon, ifc_category: null, thickness_m: null, fraction: null, mass_kg: null }
}

function element(id: string, overrides: Partial<ElementSummary> = {}): ElementSummary {
  return {
    express_id: 1,
    global_id: id,
    ifc_class: 'IfcWall',
    name: id,
    type_name: null,
    storey: 'Level 0',
    materials: [],
    layers: [],
    material_category: 'concrete',
    volume_m3: 1,
    volume_source: 'quantity',
    mass_kg: 2400,
    carbon_kgco2e: 312,
    has_geometry: true,
    is_assembly: false,
    partially_classified: false,
    ...overrides,
  }
}

const wall = element('wall', {
  layers: [layer('Brick', 'masonry', 0.3, 100), layer('Wool', 'insulation', 0.5, 50), layer('Mystery', null, 0.2, null)],
  material_category: 'insulation',
  carbon_kgco2e: 150,
  partially_classified: true,
})

describe('categoriesOf', () => {
  it('lists every layer that has volume, unclassified included', () => {
    expect(categoriesOf(wall)).toEqual(['masonry', 'insulation', 'unclassified'])
  })
  it('falls back to the element category without layers', () => {
    expect(categoriesOf(element('slab'))).toEqual(['concrete'])
  })
})

describe('matchesFocus', () => {
  it('matches a material when any layer has it', () => {
    expect(matchesFocus(wall, { kind: 'material', key: 'masonry', label: 'Masonry' })).toBe(true)
    expect(matchesFocus(wall, { kind: 'material', key: 'steel', label: 'Steel' })).toBe(false)
  })
  it('matches storeys, classes and quality issues', () => {
    expect(matchesFocus(wall, { kind: 'storey', key: 'Level 0', label: '' })).toBe(true)
    expect(matchesFocus(wall, { kind: 'class', key: 'IfcSlab', label: '' })).toBe(false)
    expect(matchesFocus(wall, { kind: 'quality', key: 'partial', label: '' })).toBe(true)
    expect(matchesFocus(wall, null)).toBe(true)
  })
})

describe('hasIssue', () => {
  it('never flags assemblies', () => {
    const assembly = element('cw', { is_assembly: true, material_category: null, volume_m3: null })
    expect(hasIssue(assembly, 'unclassified')).toBe(false)
    expect(hasIssue(assembly, 'no-volume')).toBe(false)
  })
})

describe('storeyMaterialStacks', () => {
  it('splits each storey by material and keeps the elevation order', () => {
    const stacks = storeyMaterialStacks(
      [wall, element('slab', { storey: 'Level 1' }), element('cw', { is_assembly: true, storey: 'Level 1' })],
      ['Level 0', 'Level 1'],
    )
    expect(stacks.map((s) => s.storey)).toEqual(['Level 0', 'Level 1'])
    expect(stacks[0]!.segments).toEqual([
      { category: 'masonry', carbon: 100 },
      { category: 'insulation', carbon: 50 },
    ])
    expect(stacks[1]!.total).toBe(312)
  })
})
