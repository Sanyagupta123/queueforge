from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import DATABASE_PATH
from app.database import initialize_database
from app.queue.engine import QueueEngine, QueueError
from app.schemas import (
    ClaimRequest,
    DemoRequest,
    DemoResponse,
    FailRequest,
    Health,
    Job,
    JobList,
    LeaseRequest,
    PublishRequest,
    QueueStats,
    WorkerState,
)
from app.workers.worker import WorkerManager


def create_app(database_path: str | Path = DATABASE_PATH) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        initialize_database(database_path)
        application.state.engine = QueueEngine(database_path)
        application.state.workers = WorkerManager(application.state.engine)
        yield
        await application.state.workers.stop()

    application = FastAPI(title="QueueForge API", version="1.0.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.exception_handler(QueueError)
    async def queue_error_handler(_: Request, error: QueueError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": str(error)})

    @application.exception_handler(ValueError)
    async def value_error_handler(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    def engine(request: Request) -> QueueEngine:
        return request.app.state.engine

    def workers(request: Request) -> WorkerManager:
        return request.app.state.workers

    @application.get("/health", response_model=Health)
    def health() -> Health:
        return Health()

    @application.post("/api/jobs", response_model=Job, status_code=201)
    def publish(body: PublishRequest, request: Request) -> dict:
        return engine(request).publish(body.queue_name, body.task_type, body.payload, body.max_attempts)

    @application.post("/api/jobs/claim", response_model=Job | None)
    def claim(body: ClaimRequest, request: Request) -> dict | None:
        return engine(request).claim(body.queue_name, body.worker_id, body.lease_seconds)

    @application.post("/api/jobs/{job_id}/ack", response_model=Job)
    def ack(job_id: str, body: LeaseRequest, request: Request) -> dict:
        return engine(request).ack(job_id, body.worker_id, body.lease_token)

    @application.post("/api/jobs/{job_id}/fail", response_model=Job)
    def fail(job_id: str, body: FailRequest, request: Request) -> dict:
        return engine(request).fail(job_id, body.worker_id, body.lease_token, body.error)

    @application.get("/api/jobs", response_model=JobList)
    def list_jobs(
        request: Request,
        queue_name: str | None = Query(default=None, max_length=64),
        status: Literal["queued", "leased", "succeeded", "dead"] | None = None,
        search: str | None = Query(default=None, max_length=64),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        items, total = engine(request).list_jobs(queue_name, status, search, limit, offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @application.get("/api/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str, request: Request) -> dict:
        return engine(request).get(job_id)

    @application.get("/api/stats", response_model=QueueStats)
    def stats(request: Request) -> dict:
        return engine(request).stats()

    @application.get("/api/workers", response_model=list[WorkerState])
    def list_workers(request: Request) -> list[dict]:
        return workers(request).list()

    @application.post("/api/workers/start", response_model=list[WorkerState])
    async def start_workers(request: Request, queue_name: str = "default", count: int = Query(default=2, ge=1, le=8)) -> list[dict]:
        return await workers(request).start(queue_name, count)

    @application.post("/api/workers/stop", response_model=list[WorkerState])
    async def stop_workers(request: Request, queue_name: str | None = None) -> list[dict]:
        return await workers(request).stop(queue_name)

    @application.post("/api/demo/run", response_model=DemoResponse)
    async def run_demo(body: DemoRequest, request: Request) -> dict:
        queue_engine = engine(request)
        for index in range(body.jobs):
            if index % 5 == 4:
                task_type, payload = "simulate_failure", {"fail_attempts": 1}
            elif index % 2:
                task_type, payload = "calculate_sum", {"values": [index, index + 1, 3]}
            else:
                task_type, payload = "uppercase_text", {"text": f"QueueForge demo job {index + 1}"}
            queue_engine.publish(body.queue_name, task_type, payload)
        running = await workers(request).start(body.queue_name, body.workers)
        return {"published": body.jobs, "workers": running}

    @application.get("/api/activity")
    def activity(request: Request, limit: int = Query(default=30, ge=1, le=100)) -> list[dict]:
        return engine(request).recent_events(limit)

    return application
