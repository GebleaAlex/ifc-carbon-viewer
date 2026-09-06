import { describe, expect, it } from 'vitest'
import {
  CARBON_RAMP,
  UNCLASSIFIED_COLOR,
  carbonColor,
  classColor,
  formatCarbon,
  materialColor,
  rampColor,
} from './colors'

describe('rampColor', () => {
  it('returns the ramp ends at 0 and 1', () => {
    expect(rampColor(0)).toBe(CARBON_RAMP[0])
    expect(rampColor(1)).toBe(CARBON_RAMP[CARBON_RAMP.length - 1])
  })

  it('clamps out-of-range and non-finite input', () => {
    expect(rampColor(-3)).toBe(CARBON_RAMP[0])
    expect(rampColor(7)).toBe(CARBON_RAMP[CARBON_RAMP.length - 1])
    expect(rampColor(Number.NaN)).toBe(CARBON_RAMP[0])
  })

  it('interpolates between two stops', () => {
    expect(rampColor(0.5, ['#000000', '#ffffff'])).toBe('#808080')
  })
})

describe('carbonColor', () => {
  it('is grey when there is no estimate', () => {
    expect(carbonColor(null, 100)).toBe(UNCLASSIFIED_COLOR)
    expect(carbonColor(10, 0)).toBe(UNCLASSIFIED_COLOR)
  })

  it('maps the maximum to the hottest colour', () => {
    expect(carbonColor(100, 100)).toBe(CARBON_RAMP[CARBON_RAMP.length - 1])
  })
})

describe('classColor', () => {
  it('is stable for the same class and different for unknown classes', () => {
    expect(classColor('IfcWall')).toBe(classColor('IfcWall'))
    expect(classColor('IfcSomethingNew')).toMatch(/^#[0-9a-f]{6}$/)
  })
})

describe('materialColor', () => {
  it('falls back to grey for unknown or missing categories', () => {
    expect(materialColor(null, { steel: '#f97316' })).toBe(UNCLASSIFIED_COLOR)
    expect(materialColor('steel', { steel: '#f97316' })).toBe('#f97316')
    expect(materialColor('foam', { steel: '#f97316' })).toBe(UNCLASSIFIED_COLOR)
  })
})

describe('formatCarbon', () => {
  it('switches to tonnes above 1000 kg', () => {
    expect(formatCarbon(312.4)).toBe('312 kg')
    expect(formatCarbon(7490)).toBe('7.49 t')
    expect(formatCarbon(null)).toBe('–')
  })
})
