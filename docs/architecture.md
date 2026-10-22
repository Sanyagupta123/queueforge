# Architecture

## Component responsibilities

- `app/database.py` initializes SQLite tables, indexes, WAL, foreign keys, and connection lifecycle.
- `app/queue/engine.py` owns persistence, queue transitions, lease recovery, event recording, and statistics.
- `app/queue/retry.py` provides deterministic exponential retry delays.
- `app/workers/worker.py` owns worker task lifecycle and calls the allowlisted handlers without holding a database transaction.
- `app/workers/demo_tasks.py` validates and executes the three supported demo task types.
- `app/api.py` validates HTTP requests, maps queue errors to HTTP status codes, and manages application lifespan.
- `frontend/src/api.ts` and `frontend/src/App.tsx` provide the typed API integration and operational dashboard.

## Job schema and state machine

Jobs move from `queued` to `leased`, then either `succeeded`, `queued` for retry, or `dead`. Terminal jobs are not claimable. A job row stores JSON payload/result, retry limit/count, creation and availability times, current lease owner/expiry/token, completion time, claim timestamps, and bounded error text. The `events` table records publication, claim, retry, success, recovery, and dead-letter events.

Indexes support queue/status/availability FIFO scans, lease expiry scans, recent completions, and activity history. Timestamps are Unix seconds.

## Atomic claim and recovery

Claim begins a short `BEGIN IMMEDIATE` transaction, recovers expired leases for the requested queue, selects the oldest eligible job, conditionally changes it from queued to leased, increments the attempt and fencing token, assigns the worker, records the lease expiry/event, and commits before execution. SQLite serializes concurrent writers, so workers with independent connections cannot claim the same currently eligible row.

Recovery is idempotent and transactional. A lease with attempts remaining returns to queued with the retry delay; an exhausted lease becomes dead. Recovery clears the prior owner and expiry but retains the attempt count and fencing generation.

## Retry and fencing

Delay after a failed or expired attempt is `min(base_seconds * 2 ** (attempts - 1), max_seconds)`, with defaults of 1 and 60 seconds. ACK and failure require leased state, matching worker, matching token, and an unexpired lease. Each new claim increments the token, preventing an older lease from modifying current queue state.

## Worker lifecycle and metrics

Workers poll asynchronously, claim through the engine, execute only a static task allowlist, then ACK or fail. Cancellation never ACKs interrupted work; its lease remains for later recovery. Statistics derive counts and event/timestamp intervals from SQLite. Processing duration is completion minus last claim; queue wait is first claim minus creation; retry rate is scheduled retries divided by claims in the last hour; throughput is successful completions in the last hour divided by 60.

The dashboard chart groups actual persisted events into five-minute buckets for the trailing hour. Worker status is from live tasks in this API process, not a persisted or cross-process heartbeat.

## Trade-offs

SQLite is simple and durable for a local MVP. WAL improves simultaneous readers and a writer, but SQLite still permits only one writer at a time. For multi-node scale, the engine/repository boundary could be backed by PostgreSQL with row-level locking or a broker, while preserving the API and delivery contract.
