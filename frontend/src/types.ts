export type JobStatus = 'queued' | 'leased' | 'succeeded' | 'dead'

export interface Job {
  id: string
  queue_name: string
  task_type: string
  payload: Record<string, unknown>
  result: unknown | null
  status: JobStatus
  attempts: number
  max_attempts: number
  created_at: number
  available_at: number
  lease_until: number | null
  worker_id: string | null
  lease_token: number
  last_error: string | null
  completed_at: number | null
  first_claimed_at: number | null
  last_claimed_at: number | null
}

export interface PublishRequest {
  queue_name: string
  task_type: string
  payload: Record<string, unknown>
  max_attempts: number
}

export interface WorkerStatus {
  worker_id: string
  queue_name: string
  status: 'running' | 'stopped'
  current_job_id: string | null
  processed_jobs: number
  last_activity_at: number | null
}

export interface QueueStats {
  counts: Record<JobStatus, number>
  queue_depth: Array<{ queue_name: string; status: JobStatus; count: number }>
  completed_last_hour: number
  throughput_per_minute: number | null
  average_processing_seconds: number | null
  average_queue_wait_seconds: number | null
  retry_rate: number | null
}

export interface JobList {
  items: Job[]
  total: number
  limit: number
  offset: number
}

export interface QueueEvent {
  id: number
  job_id: string
  event_type: string
  worker_id: string | null
  created_at: number
  details: string | null
}

export interface ApiError {
  detail: string
}
