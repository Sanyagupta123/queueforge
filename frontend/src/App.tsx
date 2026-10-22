import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowDownToLine, Check, ChevronDown, CircleAlert, Clock3, Database,
  Play, RefreshCw, Search, Server, Square, Terminal, X,
} from 'lucide-react'
import { api } from './api'
import type { Job, JobStatus, QueueEvent, QueueStats, WorkerStatus } from './types'

const ActivityChart = lazy(() => import('./components/ActivityChart'))
const statuses: Array<JobStatus | 'all'> = ['all', 'queued', 'leased', 'succeeded', 'dead']
const samplePayloads: Record<string, string> = {
  uppercase_text: '{\n  "text": "hello queueforge"\n}',
  calculate_sum: '{\n  "values": [12, 28, 5]\n}',
  simulate_failure: '{\n  "fail_attempts": 1\n}',
}

function timestamp(value: number | null): string {
  return value == null ? '—' : new Date(value * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function App() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [stats, setStats] = useState<QueueStats | null>(null)
  const [workers, setWorkers] = useState<WorkerStatus[]>([])
  const [events, setEvents] = useState<QueueEvent[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [queue, setQueue] = useState('default')
  const [filter, setFilter] = useState<JobStatus | 'all'>('all')
  const [search, setSearch] = useState('')
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [task, setTask] = useState('uppercase_text')
  const [payload, setPayload] = useState(samplePayloads.uppercase_text)
  const [attempts, setAttempts] = useState(3)
  const [publishing, setPublishing] = useState(false)
  const refreshInFlight = useRef(false)

  const refresh = useCallback(async (initial = false) => {
    if (refreshInFlight.current) return
    refreshInFlight.current = true
    if (initial) setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '100', queue_name: queue })
      if (filter !== 'all') params.set('status', filter)
      if (search.trim()) params.set('search', search.trim())
      const [health, list, nextStats, nextWorkers, nextEvents] = await Promise.all([
        api.health(), api.jobs(params), api.stats(), api.workers(), api.activity(),
      ])
      setConnected(health.status === 'ok')
      setJobs(list.items)
      setStats(nextStats)
      setWorkers(nextWorkers.filter((worker) => worker.queue_name === queue))
      setEvents(nextEvents)
      setError('')
      setSelected((current) => current ? list.items.find((job) => job.id === current.id) ?? current : null)
    } catch (reason) {
      setConnected(false)
      setError(reason instanceof Error ? reason.message : 'Unable to load queue data')
    } finally {
      setLoading(false)
      refreshInFlight.current = false
    }
  }, [queue, filter, search])

  useEffect(() => {
    let active = true
    let timer: number | undefined
    const poll = async (initial = false) => {
      if (!active) return
      await refresh(initial)
      if (active) timer = window.setTimeout(() => { void poll() }, 5000)
    }
    void poll(true)
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer) }
  }, [refresh])

  const filteredJobs = useMemo(() => jobs, [jobs])
  const queueCounts = stats?.queue_depth.filter((entry) => entry.queue_name === queue) ?? []
  const countFor = (status: JobStatus) => queueCounts.find((entry) => entry.status === status)?.count ?? 0
  const timeline = useMemo(() => {
    const hour = Date.now() / 1000 - 3600
    const buckets = Array.from({ length: 12 }, (_, index) => ({
      label: new Date((hour + index * 300) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      succeeded: 0,
      failed: 0,
    }))
    events.forEach((event) => {
      if (event.created_at < hour) return
      const index = Math.min(11, Math.floor((event.created_at - hour) / 300))
      if (event.event_type === 'succeeded') buckets[index].succeeded += 1
      if (event.event_type === 'dead' || event.event_type === 'retry_scheduled') buckets[index].failed += 1
    })
    return buckets
  }, [events])

  async function publish(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    let parsed: unknown
    try {
      parsed = JSON.parse(payload)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Payload must be a JSON object')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : 'Invalid JSON payload')
      return
    }
    setPublishing(true)
    setNotice('')
    try {
      await api.publish({ queue_name: queue, task_type: task, payload: parsed as Record<string, unknown>, max_attempts: attempts })
      setNotice('Job published to the durable queue.')
      await refresh()
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : 'Job could not be published')
    } finally {
      setPublishing(false)
    }
  }

  async function workerAction(action: 'start' | 'stop' | 'demo') {
    try {
      if (action === 'start') await api.startWorkers(queue)
      else if (action === 'stop') await api.stopWorkers(queue)
      else {
        const result = await api.runDemo(queue)
        setNotice(`Demo workload published: ${result.published} jobs. These run through the real queue.`)
      }
      await refresh()
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : 'Worker action failed')
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="QueueForge home"><span className="brand-mark"><Database size={19} /></span><span>queue<span className="brand-accent">forge</span></span></a>
        <div className="workspace-label">WORKSPACE</div>
        <button className="side-link active"><Activity size={17} /> Queue overview <span className="side-dot" /></button>
        <div className="sidebar-bottom">
          <div className="connection-card"><span className={`connection-dot ${connected ? 'online' : ''}`} /><div><b>{connected ? 'API connected' : 'API offline'}</b><small>127.0.0.1:8000</small></div></div>
          <div className="sidebar-foot">QUEUEFORGE <span>v1.0.0 · LOCAL</span></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">Queues <span>/</span> <b>Overview</b></div>
          <div className="top-actions">
            <label className="queue-picker"><span>QUEUE</span><select value={queue} onChange={(event) => setQueue(event.target.value)} aria-label="Selected queue"><option value="default">default</option><option value="demo">demo</option></select><ChevronDown size={13} /></label>
            <span className={`service-pill ${connected ? 'is-online' : 'is-offline'}`}><i /> {connected ? 'SERVICE ONLINE' : 'SERVICE OFFLINE'}</span>
            <button className="icon-button" aria-label="Refresh data" onClick={() => void refresh()}><RefreshCw size={16} /></button>
          </div>
        </header>

        {error && <div className="error-banner"><CircleAlert size={16} />{error}<button onClick={() => void refresh()}>Retry</button></div>}
        {notice && <div className="notice-banner"><Check size={16} />{notice}<button aria-label="Dismiss message" onClick={() => setNotice('')}><X size={15} /></button></div>}

        <section className="page-heading"><div><div className="eyebrow">SYSTEM MONITOR <span className="live-pulse" /></div><h1>Queue overview</h1><p>Monitor message flow, workers, and delivery health.</p></div><button className="button button-secondary" onClick={() => void workerAction('demo')} disabled={!connected}><Play size={15} fill="currentColor" /> Run demo workload</button></section>

        <section className="summary-grid" aria-label="Queue state summary">
          {([
            ['Queued', countFor('queued'), 'var(--cyan)', ArrowDownToLine],
            ['Leased', countFor('leased'), 'var(--amber)', Clock3],
            ['Succeeded', countFor('succeeded'), 'var(--green)', Check],
            ['Dead letter', countFor('dead'), 'var(--red)', CircleAlert],
          ] as const).map(([label, value, color, Icon]) => (
            <article className="summary-card" key={label}><div className="summary-top"><span>{label.toUpperCase()}</span><Icon size={16} color={color} /></div><div className="summary-value">{loading ? '—' : value.toLocaleString()}</div><div className="summary-foot"><span className="mini-indicator" style={{ background: color }} /> Live queue state</div></article>
          ))}
        </section>

        <div className="dashboard-grid">
          <section className="panel chart-panel">
            <div className="panel-heading"><div><h2>Recent activity</h2><p>Persisted queue events · last hour</p></div><span className="panel-icon"><Activity size={16} /></span></div>
            {events.length ? <Suspense fallback={<div className="chart-empty">Loading activity chart…</div>}><ActivityChart data={timeline} /></Suspense> : <div className="chart-empty"><Activity size={22} /><span>Queue event history will appear here as jobs run.</span></div>}
            <div className="chart-legend"><span><i className="legend-green" />Succeeded</span><span><i className="legend-amber" />Retry / dead</span><span className="chart-note">5-minute buckets · real events</span></div>
          </section>

          <section className="panel metrics-panel">
            <div className="panel-heading"><div><h2>Performance</h2><p>Measured from persisted job timestamps</p></div><span className="panel-icon"><Server size={16} /></span></div>
            <div className="metric-row"><div><span>COMPLETED / HOUR</span><b>{stats?.completed_last_hour ?? '—'}</b></div><div><span>AVG. PROCESSING</span><b>{stats?.average_processing_seconds == null ? '—' : `${stats.average_processing_seconds.toFixed(2)}s`}</b></div></div>
            <div className="metric-row"><div><span>AVG. QUEUE WAIT</span><b>{stats?.average_queue_wait_seconds == null ? '—' : `${stats.average_queue_wait_seconds.toFixed(2)}s`}</b></div><div><span>RETRY RATE</span><b>{stats?.retry_rate == null ? '—' : `${(stats.retry_rate * 100).toFixed(1)}%`}</b></div></div>
            <div className="measurement-note"><i /> Metrics are unavailable until there is enough execution history.</div>
          </section>
        </div>

        <section className="panel worker-panel">
          <div className="panel-heading"><div><h2>Workers</h2><p>Runtime workers · queue <code>{queue}</code></p></div><div className="worker-actions"><button className="button button-secondary small" onClick={() => void workerAction('start')} disabled={!connected}><Play size={13} /> Start 2 workers</button><button className="button button-danger small" onClick={() => void workerAction('stop')} disabled={!connected || workers.length === 0}><Square size={12} /> Stop workers</button></div></div>
          {workers.length ? <div className="worker-list">{workers.map((worker) => <div className="worker-item" key={worker.worker_id}><span className="worker-avatar"><Terminal size={15} /></span><div className="worker-name"><b>{worker.worker_id}</b><small>{worker.current_job_id ? `Processing ${worker.current_job_id.slice(0, 10)}…` : 'Polling for available jobs'}</small></div><span className="worker-stat">{worker.processed_jobs} <small>processed</small></span><span className="worker-live"><i /> RUNNING</span></div>)}</div> : <div className="empty-inline"><span className="empty-icon"><Server size={16} /></span><span><b>No active workers</b><small>Start workers to process jobs from this queue.</small></span><button className="text-button" onClick={() => void workerAction('start')} disabled={!connected}>Start workers <span>→</span></button></div>}
        </section>

        <div className="lower-grid">
          <section className="panel publish-panel">
            <div className="panel-heading"><div><h2>Publish a job</h2><p>Send a task to the durable queue</p></div><span className="panel-icon"><ArrowDownToLine size={16} /></span></div>
            <form onSubmit={(event) => void publish(event)}>
              <label className="form-label" htmlFor="task-type">TASK HANDLER</label>
              <select id="task-type" className="control" value={task} onChange={(event) => { setTask(event.target.value); setPayload(samplePayloads[event.target.value]) }}>
                <option value="uppercase_text">uppercase_text</option><option value="calculate_sum">calculate_sum</option><option value="simulate_failure">simulate_failure</option>
              </select>
              <label className="form-label" htmlFor="job-payload">JSON PAYLOAD</label>
              <textarea id="job-payload" className="control payload-editor" value={payload} onChange={(event) => setPayload(event.target.value)} spellCheck={false} />
              <div className="form-row"><label className="form-label" htmlFor="max-attempts">MAX ATTEMPTS</label><select id="max-attempts" className="control attempt-select" value={attempts} onChange={(event) => setAttempts(Number(event.target.value))}>{[1, 2, 3, 5, 10].map((value) => <option key={value} value={value}>{value} attempts</option>)}</select></div>
              <button className="button button-primary publish-button" type="submit" disabled={publishing || !connected}><ArrowDownToLine size={15} />{publishing ? 'Publishing…' : 'Publish to queue'}</button>
            </form>
          </section>

          <section className="panel jobs-panel">
            <div className="panel-heading jobs-heading"><div><h2>Job explorer <span className="total-badge">{jobs.length}</span></h2><p>Inspect and filter recent queue jobs</p></div><div className="search-box"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search job ID" aria-label="Search by job ID" /></div></div>
            <div className="filter-tabs" role="tablist" aria-label="Filter job status">{statuses.map((status) => <button key={status} role="tab" aria-selected={filter === status} className={filter === status ? 'selected' : ''} onClick={() => setFilter(status)}>{status === 'all' ? 'All jobs' : status === 'dead' ? 'Dead letter' : status[0].toUpperCase() + status.slice(1)}{status !== 'all' && <span>{countFor(status)}</span>}</button>)}</div>
            <div className="table-wrap"><table><thead><tr><th>JOB / TASK</th><th>STATUS</th><th>ATTEMPTS</th><th>WORKER</th><th>CREATED</th></tr></thead><tbody>
              {filteredJobs.map((job) => <tr key={job.id} onClick={() => setSelected(job)} className={selected?.id === job.id ? 'row-selected' : ''} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') setSelected(job) }}><td><b className="job-id">{job.id.slice(0, 12)}</b><small>{job.task_type}</small></td><td><span className={`status status-${job.status}`}><i />{job.status}</span></td><td className="attempt-cell">{job.attempts}<span> / {job.max_attempts}</span></td><td className="worker-cell">{job.worker_id ?? '—'}</td><td className="time-cell">{timestamp(job.created_at)}</td></tr>)}
            </tbody></table>{!filteredJobs.length && <div className="table-empty">{loading ? 'Loading jobs…' : 'No jobs match this queue and filter.'}</div>}</div>
            <div className="table-footer">Showing {jobs.length} recent jobs <span>Maximum 100 · newest first</span></div>
          </section>
        </div>
        <footer className="page-footer"><span>QueueForge <b>·</b> SQLite-backed local message queue</span><span>Delivery guarantee: at-least-once <i /></span></footer>
      </main>

      {selected && <div className="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) setSelected(null) }}><section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="detail-title"><div className="detail-head"><div><div className="eyebrow">JOB DETAILS</div><h2 id="detail-title">{selected.id}</h2></div><button className="icon-button" aria-label="Close details" onClick={() => setSelected(null)}><X size={17} /></button></div><div className="detail-content"><div className="detail-pills"><span className={`status status-${selected.status}`}><i />{selected.status}</span><code>{selected.task_type}</code></div><div className="detail-grid"><span>Queue<b>{selected.queue_name}</b></span><span>Attempts<b>{selected.attempts} / {selected.max_attempts}</b></span><span>Worker<b>{selected.worker_id ?? '—'}</b></span><span>Lease token<b>{selected.lease_token}</b></span><span>Created<b>{timestamp(selected.created_at)}</b></span><span>First claimed<b>{timestamp(selected.first_claimed_at)}</b></span><span>Completed<b>{timestamp(selected.completed_at)}</b></span><span>Lease expiry<b>{timestamp(selected.lease_until)}</b></span></div><h3>Payload</h3><pre>{JSON.stringify(selected.payload, null, 2)}</pre>{selected.result != null && <><h3>Result</h3><pre>{JSON.stringify(selected.result, null, 2)}</pre></>}{selected.last_error && <div className="job-error"><b>Last error</b><p>{selected.last_error}</p></div>}</div></section></div>}
    </div>
  )
}

export default App
