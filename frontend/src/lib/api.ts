import type {
  SyncStatus,
  Image,
  SyncRun,
  AppConfig,
  FilterOptions,
  FilterValues,
  PaginatedResponse,
  BatchSyncConfig,
  BatchSyncStatus,
  BatchSyncState,
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

export async function triggerSync(
  fullSync = false,
  maxRecords?: number
): Promise<{ message: string; run_id: string; max_records?: number }> {
  const params = new URLSearchParams({ full_sync: String(fullSync) })
  if (maxRecords) params.append('max_records', String(maxRecords))
  return fetchApi(`/sync?${params}`, { method: 'POST' })
}

export async function getSyncRuns(limit = 20): Promise<SyncRun[]> {
  const data = await fetchApi<{ runs: SyncRun[] }>(`/runs?limit=${limit}`)
  return data.runs
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
  if (filters.photo_origin) params.append('photo_origin', filters.photo_origin)
  if (filters.search) params.append('search', filters.search)
  if (filters.date_from) params.append('date_from', filters.date_from)
  if (filters.date_to) params.append('date_to', filters.date_to)

  const data = await fetchApi<{ images: Image[]; count: number }>(`/images?${params}`)
  return {
    items: data.images,
    total: data.count,
    limit,
    offset,
  }
}

export async function getFilterValues(): Promise<FilterValues> {
  try {
    return await fetchApi<FilterValues>('/images/filters')
  } catch {
    // Endpoint may not exist yet
    return { job_captain_timesheets: [], project_names: [], departments: [], photo_origins: [] }
  }
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
export async function getConfig(): Promise<AppConfig | null> {
  try {
    return await fetchApi<AppConfig>('/config')
  } catch {
    // Config endpoint may not exist yet
    return null
  }
}

export async function updateConfig(config: Partial<AppConfig>): Promise<AppConfig | null> {
  try {
    return await fetchApi<AppConfig>('/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    })
  } catch {
    return null
  }
}

export async function testZohoConnection(): Promise<{ success: boolean; message: string; records_count?: number }> {
  try {
    return await fetchApi('/config/test-zoho', { method: 'POST' })
  } catch {
    return { success: false, message: 'Config endpoint not available' }
  }
}

// Batch Sync
export async function getBatchSyncStatus(): Promise<BatchSyncStatus> {
  return fetchApi<BatchSyncStatus>('/sync/batch')
}

export async function getBatchSyncDetails(batchId: string): Promise<BatchSyncState> {
  return fetchApi<BatchSyncState>(`/sync/batch/${batchId}`)
}

export async function startBatchSync(config: BatchSyncConfig): Promise<{ message: string; batch_id: string }> {
  return fetchApi('/sync/batch', {
    method: 'POST',
    body: JSON.stringify(config),
  })
}

export async function pauseBatchSync(batchId: string): Promise<{ message: string }> {
  return fetchApi(`/sync/batch/${batchId}/pause`, { method: 'POST' })
}

export async function resumeBatchSync(batchId: string): Promise<{ message: string }> {
  return fetchApi(`/sync/batch/${batchId}/resume`, { method: 'POST' })
}

export async function cancelBatchSync(batchId: string): Promise<{ message: string }> {
  return fetchApi(`/sync/batch/${batchId}/cancel`, { method: 'POST' })
}

// Quick Batch Sync - "Download Next N Photos"
export interface QuickBatchStatus {
  oldest_synced_date: string | null
  total_synced: number
}

export interface QuickBatchResponse {
  message: string
  run_id: string
  count: number
  oldest_synced_date: string | null
}

export async function getQuickBatchStatus(): Promise<QuickBatchStatus> {
  return fetchApi<QuickBatchStatus>('/sync/quick-batch/status')
}

export async function startQuickBatch(count: number = 100): Promise<QuickBatchResponse> {
  return fetchApi(`/sync/quick-batch?count=${count}`, { method: 'POST' })
}
