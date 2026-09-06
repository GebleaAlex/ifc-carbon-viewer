import type { CarbonSummary, ElementDetail, ElementSummary, MaterialFactor, ModelSummary } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  listModels: () => request<ModelSummary[]>('/api/models'),
  getModel: (id: string) => request<ModelSummary>(`/api/models/${id}`),
  deleteModel: (id: string) => request<void>(`/api/models/${id}`, { method: 'DELETE' }),
  uploadModel: (file: File) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return request<ModelSummary>('/api/models', { method: 'POST', body: form })
  },
  listElements: (id: string) => request<ElementSummary[]>(`/api/models/${id}/elements`),
  getElement: (id: string, globalId: string) =>
    request<ElementDetail>(`/api/models/${id}/elements/${encodeURIComponent(globalId)}`),
  getCarbon: (id: string) => request<CarbonSummary>(`/api/models/${id}/carbon`),
  getFactors: () => request<MaterialFactor[]>('/api/carbon/factors'),
  geometryUrl: (id: string) => `${BASE}/api/models/${id}/geometry.glb`,
}
