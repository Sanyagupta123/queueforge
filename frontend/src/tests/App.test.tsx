import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { Job, QueueStats } from '../types'

const apiMock = vi.hoisted(() => ({
  health: vi.fn(),
  jobs: vi.fn(),
  stats: vi.fn(),
  workers: vi.fn(),
  activity: vi.fn(),
  publish: vi.fn(),
  startWorkers: vi.fn(),
  stopWorkers: vi.fn(),
  runDemo: vi.fn(),
}))

vi.mock('../api', () => ({ api: apiMock }))

const job = (id: string, status: Job['status']): Job => ({
  id, queue_name: 'default', task_type: 'uppercase_text', payload: { text: 'test' },
  result: null, status, attempts: 0, max_attempts: 3, created_at: 1_700_000_000,
  available_at: 1_700_000_000, lease_until: null, worker_id: null, lease_token: 0,
  last_error: null, completed_at: null, first_claimed_at: null, last_claimed_at: null,
})

const stats: QueueStats = {
  counts: { queued: 1, leased: 0, succeeded: 2, dead: 0 },
  queue_depth: [
    { queue_name: 'default', status: 'queued', count: 1 },
    { queue_name: 'default', status: 'succeeded', count: 2 },
  ],
  completed_last_hour: 2,
  throughput_per_minute: 2 / 60,
  average_processing_seconds: 1,
  average_queue_wait_seconds: 0.5,
  retry_rate: null,
}

describe('Queue dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.health.mockResolvedValue({ status: 'ok' })
    apiMock.jobs.mockImplementation(async (params: URLSearchParams) => {
      const selected = params.get('status')
      const items = [job('queued-job-123456', 'queued'), job('done-job-123456', 'succeeded')]
        .filter((item) => !selected || item.status === selected)
      return { items, total: items.length, limit: 100, offset: 0 }
    })
    apiMock.stats.mockResolvedValue(stats)
    apiMock.workers.mockResolvedValue([])
    apiMock.activity.mockResolvedValue([])
  })

  it('renders backend counts and filters the displayed jobs', async () => {
    render(<App />)
    expect(await screen.findByText('queued-job-1')).toBeInTheDocument()
    expect(screen.getByText('2', { selector: '.summary-value' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /Succeeded/ }))
    await waitFor(() => expect(screen.queryByText('queued-job-1')).not.toBeInTheDocument())
    expect(screen.getByText('done-job-123')).toBeInTheDocument()
  })

  it('does not publish invalid JSON', async () => {
    render(<App />)
    await screen.findByText('queued-job-1')
    fireEvent.change(screen.getByLabelText('JSON PAYLOAD'), { target: { value: '{broken' } })
    fireEvent.click(screen.getByRole('button', { name: /Publish to queue/ }))
    expect(await screen.findByText(/position 1/)).toBeInTheDocument()
    expect(apiMock.publish).not.toHaveBeenCalled()
  })

  it('surfaces API unavailability', async () => {
    apiMock.health.mockRejectedValue(new Error('API is unavailable'))
    render(<App />)
    expect(await screen.findByText('API is unavailable')).toBeInTheDocument()
  })
})
