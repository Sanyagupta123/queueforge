import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.config import DEFAULT_LEASE_SECONDS
from app.queue.engine import InvalidTransition, QueueEngine
from app.workers.demo_tasks import execute


@dataclass
class RuntimeWorker:
    worker_id: str
    queue_name: str
    task: asyncio.Task[None]
    current_job_id: str | None = None
    processed_jobs: int = 0
    last_activity_at: float | None = None


class WorkerManager:
    def __init__(self, engine: QueueEngine, concurrency: int = 2, poll_seconds: float = 0.25):
        self.engine = engine
        self.concurrency = concurrency
        self.poll_seconds = poll_seconds
        self.workers: dict[str, RuntimeWorker] = {}
        self._lock = asyncio.Lock()

    async def start(self, queue_name: str, count: int | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            desired = count if count is not None else self.concurrency
            if not 1 <= desired <= 8:
                raise ValueError("worker count must be between 1 and 8")
            active_for_queue = [w for w in self.workers.values() if w.queue_name == queue_name and not w.task.done()]
            created: list[RuntimeWorker] = []
            while len(active_for_queue) + len(created) < desired:
                worker_id = f"worker-{uuid.uuid4().hex[:8]}"
                placeholder = asyncio.create_task(asyncio.sleep(0), name=worker_id)
                worker = RuntimeWorker(worker_id, queue_name, placeholder)
                worker.task = asyncio.create_task(self._run(worker), name=worker_id)
                self.workers[worker_id] = worker
                created.append(worker)
            return [self._snapshot(worker) for worker in active_for_queue + created]

    async def stop(self, queue_name: str | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            targets = [w for w in self.workers.values() if queue_name is None or w.queue_name == queue_name]
            for worker in targets:
                worker.task.cancel()
        if targets:
            await asyncio.gather(*(worker.task for worker in targets), return_exceptions=True)
        async with self._lock:
            for worker in targets:
                self.workers.pop(worker.worker_id, None)
            return [self._snapshot(worker, stopped=True) for worker in targets]

    def list(self) -> list[dict[str, Any]]:
        return [self._snapshot(worker) for worker in self.workers.values() if not worker.task.done()]

    @staticmethod
    def _snapshot(worker: RuntimeWorker, stopped: bool = False) -> dict[str, Any]:
        return {
            "worker_id": worker.worker_id,
            "queue_name": worker.queue_name,
            "status": "stopped" if stopped or worker.task.done() else "running",
            "current_job_id": worker.current_job_id,
            "processed_jobs": worker.processed_jobs,
            "last_activity_at": worker.last_activity_at,
        }

    async def _run(self, worker: RuntimeWorker) -> None:
        while True:
            job = await asyncio.to_thread(
                self.engine.claim, worker.queue_name, worker.worker_id, DEFAULT_LEASE_SECONDS
            )
            if job is None:
                await asyncio.sleep(self.poll_seconds)
                continue
            worker.current_job_id = job["id"]
            worker.last_activity_at = time.time()
            try:
                result = await execute(job["task_type"], job["payload"], job["attempts"])
            except asyncio.CancelledError:
                raise
            except (ValueError, RuntimeError, TypeError, ArithmeticError) as error:
                try:
                    await asyncio.to_thread(
                        self.engine.fail, job["id"], worker.worker_id, job["lease_token"], str(error)
                    )
                except InvalidTransition:
                    pass
            else:
                try:
                    await asyncio.to_thread(
                        self.engine.ack, job["id"], worker.worker_id, job["lease_token"], result
                    )
                except InvalidTransition:
                    pass
                else:
                    worker.processed_jobs += 1
            finally:
                worker.current_job_id = None
                worker.last_activity_at = time.time()
