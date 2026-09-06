export type ModelStatus = 'processing' | 'ready' | 'failed'
export type VolumeSource = 'quantity' | 'geometry'

export interface ElementSummary {
  express_id: number
  global_id: string
  ifc_class: string
  name: string | null
  type_name: string | null
  storey: string | null
  materials: string[]
  material_category: string | null
  volume_m3: number | null
  volume_source: VolumeSource | null
  mass_kg: number | null
  carbon_kgco2e: number | null
  has_geometry: boolean
}

export interface ElementDetail extends ElementSummary {
  description: string | null
  object_type: string | null
  predefined_type: string | null
  property_sets: Record<string, Record<string, unknown>>
  quantity_sets: Record<string, Record<string, unknown>>
}

export interface CarbonBucket {
  key: string
  label: string
  element_count: number
  volume_m3: number
  mass_kg: number
  carbon_kgco2e: number
  share_percent: number
}

export interface CarbonSummary {
  total_kgco2e: number
  estimated_elements: number
  unclassified_elements: number
  missing_volume_elements: number
  by_material_category: CarbonBucket[]
  by_storey: CarbonBucket[]
  by_ifc_class: CarbonBucket[]
  top_elements: ElementSummary[]
}

export interface MaterialFactor {
  category: string
  label: string
  density_kg_m3: number
  factor_kgco2e_per_kg: number
  color: string
  keywords: string[]
  note: string | null
}

export interface ModelSummary {
  id: string
  name: string
  status: ModelStatus
  error: string | null
  created_at: string
  schema_version: string | null
  file_size_bytes: number
  element_count: number
  elements_with_geometry: number
  storeys: string[]
  ifc_classes: Record<string, number>
  total_kgco2e: number | null
  parse_seconds: number | null
  is_sample: boolean
}
