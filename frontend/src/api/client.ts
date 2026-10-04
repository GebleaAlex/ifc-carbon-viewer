import type {
  CarbonSummary,
  ElementDetail,
  ElementSummary,
  MaterialFactor,
  MaterialMapping,
  MaterialUsage,
  ModelSummary,
} from './types'

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
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail) detail = JSON.stringify(body.detail)
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Upload with progress. fetch() cannot report upload progress, so this one uses XMLHttpRequest. */
function uploadWithProgress(file: File, onProgress?: (fraction: number) => void): Promise<ModelSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', file, file.name)
    xhr.open('POST', `${BASE}/api/models`)
    xhr.responseType = 'json'
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as ModelSummary)
      else reject(new ApiError(xhr.status, (xhr.response as { detail?: string } | null)?.detail ?? xhr.statusText))
    }
    xhr.onerror = () => reject(new ApiError(0, 'Network error while uploading'))
    xhr.send(form)
  })
}

const model = (id: string) => `/api/models/${encodeURIComponent(id)}`

export const api = {
  listModels: () => request<ModelSummary[]>('/api/models'),
  getModel: (id: string) => request<ModelSummary>(model(id)),
  deleteModel: (id: string) => request<void>(model(id), { method: 'DELETE' }),
  uploadModel: uploadWithProgress,
  listElements: (id: string) => request<ElementSummary[]>(`${model(id)}/elements`),
  getElement: (id: string, globalId: string) =>
    request<ElementDetail>(`${model(id)}/elements/${encodeURIComponent(globalId)}`),
  getCarbon: (id: string) => request<CarbonSummary>(`${model(id)}/carbon`),
  getMaterials: (id: string) => request<MaterialUsage[]>(`${model(id)}/materials`),
  putMapping: (id: string, mapping: MaterialMapping) =>
    request<ModelSummary>(`${model(id)}/mapping`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(mapping),
    }),
  getFactors: () => request<MaterialFactor[]>('/api/carbon/factors'),
  geometryUrl: (id: string) => `${BASE}${model(id)}/geometry.glb`,
  csvUrl: (id: string) => `${BASE}${model(id)}/export.csv`,
  reportUrl: (id: string) => `${BASE}${model(id)}/report.json`,
}
