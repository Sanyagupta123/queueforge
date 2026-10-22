# Delivery guarantees and limitations

## At-least-once execution

QueueForge makes a job available again after an explicit failure or an expired worker lease. A worker can complete a side effect and then crash before its ACK is committed. The queue will recover and run the job again, so duplicate execution is possible. Consumers that perform external side effects should be idempotent or use their own idempotency key/transactional outbox strategy.

QueueForge does not provide exactly-once side effects.

## ACK ownership and fencing

An ACK or failure is accepted only while the job is leased, the lease belongs to the supplied worker, the fencing token matches, and the lease has not expired. Every claim increments the token. This protects QueueForge's own state from a stale worker after a newer claim. It cannot undo an external side effect a stale worker already performed.

## Visibility timeout and recovery

A lease is a visibility timeout: other workers do not claim the job while the lease is active. Once `lease_until` is reached, a subsequent claim or recovery operation atomically requeues or dead-letters the job. Built-in handlers are short; there is no lease renewal in this MVP. A long-running task can therefore be executed again after its lease expires.

## Retry and dead-letter behavior

Attempts increment when a worker claims a job. Failures and recoveries use capped exponential backoff. When `attempts` reaches `max_attempts`, a subsequent failure/recovery moves the job to `dead`. The dead state remains inspectable and is not automatically reprocessed.

## Persistence and deployment limits

SQLite is the durable source of truth for jobs and events. WAL improves read/write coexistence but SQLite still serializes writes and is not a multi-node distributed broker. Runtime worker presence is process-local and is not a durable heartbeat. This local API has no authentication or rate limiting. Do not expose it to untrusted networks.

Future distributed deployments should evaluate database row locking or a broker, durable worker heartbeats, lease renewal/fencing propagation to downstream systems, authentication, rate limits, operational backups, and migration/versioning strategy.
