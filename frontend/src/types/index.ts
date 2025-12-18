export interface Image {
  id: string
  zoho_record_id: string
  field_name: string
  original_filename: string
  storage_path: string
  file_size_bytes: number
  was_processed: boolean
  tags: string[]
  category: string | null
  description: string | null
  zoho_metadata: Record<string, unknown>
  zoho_created_at: string | null
  zoho_modified_at: string | null
  synced_at: string
  url?: string
  // Fields for categorization
  job_captain_timesheet: string | null
  project_name: string | null
  department: string | null
  photo_origin: string | null
}

export interface SyncRun {
  id: string
  started_at: string
  completed_at: string | null
  status: 'running' | 'completed' | 'completed_with_errors' | 'failed'
  records_processed: number
  images_synced: number
  images_skipped: number
  errors: number
  error_log: Array<{ record_id: string; error: string; timestamp: string }> | null
}

export interface SyncStatus {
  is_running: boolean
  stats: {
    total_images: number
    processed_images: number
  }
  recent_runs: SyncRun[]
}

export interface AppConfig {
  // Zoho Settings
  zoho_client_id: string
  zoho_client_secret: string
  zoho_refresh_token: string
  zoho_account_owner_name: string
  zoho_app_link_name: string
  zoho_report_link_name: string

  // Field Mappings
  field_job_captain_timesheet: string
  field_project_name: string
  field_department: string
  field_tags: string
  field_description: string

  // Sync Settings
  sync_cron: string
  image_max_size_mb: number
  image_max_dimension: number
  image_quality: number

  // Storage
  supabase_storage_bucket: string
}

export interface FilterOptions {
  job_captain_timesheet?: string
  project_name?: string
  department?: string
  photo_origin?: string
  search?: string
  date_from?: string
  date_to?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// Filter option values for dropdowns
export interface FilterValues {
  job_captain_timesheets: string[]
  project_names: string[]
  departments: string[]
  photo_origins: string[]
}

// Batch Sync types
export interface BatchSyncConfig {
  batch_size: number
  delay_between_batches: number
  date_from?: string
  date_to?: string
  dry_run: boolean
}

export interface BatchSyncState {
  id: string
  created_at: string
  updated_at: string
  status: 'pending' | 'running' | 'paused' | 'completed' | 'completed_with_errors' | 'cancelled' | 'failed'
  batch_size: number
  delay_between_batches: number
  date_from: string | null
  date_to: string | null
  dry_run: boolean
  current_offset: number
  total_records_estimated: number | null
  batches_completed: number
  records_processed: number
  images_synced: number
  images_skipped: number
  errors: number
  error_log: Array<{ record_id?: string; field?: string; error: string; timestamp?: string }> | null
  current_batch_started_at: string | null
  last_batch_completed_at: string | null
}

export interface BatchSyncStatus {
  active: BatchSyncState | null
  recent: BatchSyncState[]
}
