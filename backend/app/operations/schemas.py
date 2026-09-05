"""Pydantic request/response schemas for the Phase 11 Operations API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class BackupResponse(BaseModel):
    id: uuid.UUID
    status: str
    database_dump_bytes: int | None
    media_archive_bytes: int | None
    media_file_count: int | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class RetentionCleanupRunResponse(BaseModel):
    id: uuid.UUID
    dry_run: bool
    status: str
    conversations_evaluated: int
    items_deleted: int
    bytes_freed: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class RetentionCleanupItemResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    conversation_id: uuid.UUID | None
    retention_policy_id: uuid.UUID | None
    action: str
    media_asset_id: uuid.UUID | None
    transcript_id: uuid.UUID | None
    bytes_freed: int | None
    segments_deleted: int | None
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RetentionCleanupRunRequest(BaseModel):
    dry_run: bool = True


class WorkerMetrics(BaseModel):
    role: str
    job_types: list[str]
    running_jobs: int
    queued_jobs: int
    active_worker_ids: list[str]
    last_activity_at: datetime | None
    succeeded_last_1h: int
    succeeded_last_24h: int
    failed_last_24h: int
    avg_duration_seconds_last_24h: float | None
    sample_count_last_24h: int


class GpuMetrics(BaseModel):
    cuda_available: bool
    device_name: str | None
    total_vram_mb: int | None
    free_vram_mb: int | None
    utilization_percent: int | None


class QueueDepthByType(BaseModel):
    job_type: str
    queued: int
    running: int


class QueueThroughputBucket(BaseModel):
    hour_start: datetime
    succeeded: int
    failed: int


class QueueMetrics(BaseModel):
    depth_by_job_type: list[QueueDepthByType]
    throughput_hourly: list[QueueThroughputBucket]


class OperationsMetricsResponse(BaseModel):
    workers: list[WorkerMetrics]
    gpu: GpuMetrics
    queue: QueueMetrics


class ModelStorageEntry(BaseModel):
    name: str
    size_bytes: int


class ModelStorageResponse(BaseModel):
    model_volume_root: str
    total_bytes: int
    models: list[ModelStorageEntry]
