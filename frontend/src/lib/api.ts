import type {
  SyncStatus,
  Image,
  SyncRun,
  AppConfig,
  FilterOptions,
  FilterValues,
  PaginatedResponse
} from '@/types'

const API_BASE = '/api'

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || 'Request failed')
  }

  return res.json()
}

// Status & Sync
export async function getStatus(): Promise<SyncStatus> {
  return fetchApi<SyncStatus>('/status')
}

export async function triggerSync(fullSync = false): Promise<{ message: string; run_id: string }> {
  return fetchApi(`/sync?full_sync=${fullSync}`, { method: 'POST' })
}

export async function getSyncRuns(limit = 20): Promise<SyncRun[]> {
  return fetchApi<SyncRun[]>(`/runs?limit=${limit}`)
}

// Images
export async function getImages(
  filters: FilterOptions = {},
  limit = 100,
  offset = 0
): Promise<PaginatedResponse<Image>> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })

  if (filters.job_captain_timesheet) params.append('job_captain_timesheet', filters.job_captain_timesheet)
  if (filters.project_name) params.append('project_name', filters.project_name)
  if (filters.department) params.append('department', filters.department)
  if (filters.search) params.append('search', filters.search)
  if (filters.date_from) params.append('date_from', filters.date_from)
  if (filters.date_to) params.append('date_to', filters.date_to)

  return fetchApi<PaginatedResponse<Image>>(`/images?${params}`)
}

export async function getFilterValues(): Promise<FilterValues> {
  return fetchApi<FilterValues>('/images/filters')
}

// Bulk download
export async function downloadImages(imageIds: string[]): Promise<Blob> {
  const res = await fetch(`${API_BASE}/images/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_ids: imageIds }),
  })

  if (!res.ok) {
    throw new Error('Download failed')
  }

  return res.blob()
}

// Config
export async function getConfig(): Promise<AppConfig> {
  return fetchApi<AppConfig>('/config')
}

export async function updateConfig(config: Partial<AppConfig>): Promise<AppConfig> {
  return fetchApi<AppConfig>('/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

export async function testZohoConnection(): Promise<{ success: boolean; message: string; records_count?: number }> {
  return fetchApi('/config/test-zoho', { method: 'POST' })
}
