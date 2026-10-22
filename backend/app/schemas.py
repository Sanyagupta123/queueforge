from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    MAX_ATTEMPTS,
    MAX_LEASE_SECONDS,
    MAX_PAYLOAD_BYTES,
)

JobStatus = Literal["queued", "leased", "succeeded", "dead"]


class PublishRequest(BaseModel):
    queue_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    task_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1, le=MAX_ATTEMPTS)

    @field_validator("payload")
    @classmethod
    def payload_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json

        if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"payload must not exceed {MAX_PAYLOAD_BYTES} bytes")
        return value


class ClaimRequest(BaseModel):
    queue_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    worker_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=DEFAULT_LEASE_SECONDS, ge=1, le=MAX_LEASE_SECONDS)


class LeaseRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)
    lease_token: int = Field(ge=1)


class FailRequest(LeaseRequest):
    error: str = Field(min_length=1, max_length=2000)


class Job(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    queue_name: str
    task_type: str
    payload: dict[str, Any]
    result: Any | None
    status: JobStatus
    attempts: int
    max_attempts: int
    created_at: float
    available_at: float
    lease_until: float | None
    worker_id: str | None
    lease_token: int
    last_error: str | None
    completed_at: float | None
    first_claimed_at: float | None
    last_claimed_at: float | None


class JobList(BaseModel):
    items: list[Job]
    total: int
    limit: int
    offset: int


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "QueueForge"


class WorkerState(BaseModel):
    worker_id: str
    queue_name: str
    status: Literal["running", "stopped"]
    current_job_id: str | None
    processed_jobs: int
    last_activity_at: float | None


class QueueStats(BaseModel):
    counts: dict[str, int]
    queue_depth: list[dict[str, Any]]
    completed_last_hour: int
    throughput_per_minute: float | None
    average_processing_seconds: float | None
    average_queue_wait_seconds: float | None
    retry_rate: float | None


class DemoRequest(BaseModel):
    jobs: int = Field(default=12, ge=1, le=100)
    workers: int = Field(default=2, ge=1, le=8)
    queue_name: str = Field(default="demo", min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")


class DemoResponse(BaseModel):
    published: int
    workers: list[WorkerState]


class Event(BaseModel):
    id: int
    job_id: str
    event_type: str
    worker_id: str | None
    created_at: float
    details: str | None
