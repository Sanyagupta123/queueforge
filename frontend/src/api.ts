import type { Job, JobList, PublishRequest, QueueEvent, QueueStats, WorkerStatus } from './types'

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new Error(`QueueForge API is unavailable at ${baseUrl}`)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as Partial<{ detail: string }>
    throw new Error(body.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  jobs: (params: URLSearchParams) => request<JobList>(`/api/jobs?${params.toString()}`),
  job: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  stats: () => request<QueueStats>('/api/stats'),
  workers: () => request<WorkerStatus[]>('/api/workers'),
  activity: () => request<QueueEvent[]>('/api/activity?limit=12'),
  publish: (body: PublishRequest) => request<Job>('/api/jobs', { method: 'POST', body: JSON.stringify(body) }),
  startWorkers: (queue: string) => request<WorkerStatus[]>(`/api/workers/start?queue_name=${encodeURIComponent(queue)}&count=2`, { method: 'POST' }),
  stopWorkers: (queue: string) => request<WorkerStatus[]>(`/api/workers/stop?queue_name=${encodeURIComponent(queue)}`, { method: 'POST' }),
  runDemo: (queue: string) => request<{ published: number; workers: WorkerStatus[] }>('/api/demo/run', {
    method: 'POST',
    body: JSON.stringify({ queue_name: queue, jobs: 12, workers: 2 }),
  }),
}
