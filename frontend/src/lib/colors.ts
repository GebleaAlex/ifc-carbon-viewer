/** Pure colour and formatting helpers shared by the 3D viewer, legend and panels. */

export type ColorMode = 'material' | 'carbon' | 'class'

export const UNCLASSIFIED_COLOR = '#64748b'
export const SELECTION_COLOR = '#38bdf8'

/** Sequential ramp for embodied carbon: low (green) to high (red). */
export const CARBON_RAMP = ['#22c55e', '#a3e635', '#facc15', '#f97316', '#dc2626']

const CLASS_PALETTE: Record<string, string> = {
  IfcWall: '#cbd5e1',
  IfcWallStandardCase: '#cbd5e1',
  IfcSlab: '#94a3b8',
  IfcRoof: '#7dd3fc',
  IfcColumn: '#f97316',
  IfcBeam: '#fb923c',
  IfcWindow: '#38bdf8',
  IfcDoor: '#a78bfa',
  IfcCurtainWall: '#67e8f9',
  IfcStair: '#fbbf24',
  IfcStairFlight: '#fbbf24',
  IfcRailing: '#e879f9',
  IfcFooting: '#a8a29e',
  IfcPile: '#a8a29e',
  IfcCovering: '#f5f5f4',
  IfcFurnishingElement: '#c084fc',
  IfcPlate: '#93c5fd',
  IfcMember: '#fdba74',
  IfcBuildingElementProxy: '#d4d4d8',
}

const FALLBACK_PALETTE = ['#f472b6', '#34d399', '#60a5fa', '#fbbf24', '#c084fc', '#2dd4bf', '#fb7185', '#a3e635']

function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) | 0
  return Math.abs(hash)
}

export function classColor(ifcClass: string): string {
  return CLASS_PALETTE[ifcClass] ?? FALLBACK_PALETTE[hashString(ifcClass) % FALLBACK_PALETTE.length]!
}

export function materialColor(category: string | null, factorColors: Record<string, string>): string {
  if (!category) return UNCLASSIFIED_COLOR
  return factorColors[category] ?? UNCLASSIFIED_COLOR
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '')
  const value = parseInt(clean.length === 3 ? clean.replace(/(.)/g, '$1$1') : clean, 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

function rgbToHex([r, g, b]: [number, number, number]): string {
  return '#' + [r, g, b].map((c) => Math.round(Math.max(0, Math.min(255, c))).toString(16).padStart(2, '0')).join('')
}

/** Interpolate along a ramp of hex colours; t is clamped to [0, 1]. */
export function rampColor(t: number, ramp: string[] = CARBON_RAMP): string {
  if (ramp.length === 0) return UNCLASSIFIED_COLOR
  if (ramp.length === 1) return ramp[0]!
  const clamped = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0))
  const scaled = clamped * (ramp.length - 1)
  const index = Math.min(Math.floor(scaled), ramp.length - 2)
  const local = scaled - index
  const from = hexToRgb(ramp[index]!)
  const to = hexToRgb(ramp[index + 1]!)
  return rgbToHex([
    from[0] + (to[0] - from[0]) * local,
    from[1] + (to[1] - from[1]) * local,
    from[2] + (to[2] - from[2]) * local,
  ])
}

/**
 * Colour for an element's carbon value. Uses a square-root scale so a few very
 * heavy elements do not push everything else into the same shade of green.
 */
export function carbonColor(value: number | null, max: number): string {
  if (value === null || max <= 0) return UNCLASSIFIED_COLOR
  return rampColor(Math.sqrt(value / max))
}

export function formatCarbon(kg: number | null | undefined): string {
  if (kg === null || kg === undefined) return '–'
  if (Math.abs(kg) >= 1000) return `${(kg / 1000).toLocaleString('en', { maximumFractionDigits: 2 })} t`
  return `${kg.toLocaleString('en', { maximumFractionDigits: 0 })} kg`
}

export function formatNumber(value: number | null | undefined, digits = 2, unit = ''): string {
  if (value === null || value === undefined) return '–'
  return `${value.toLocaleString('en', { maximumFractionDigits: digits })}${unit ? ' ' + unit : ''}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
