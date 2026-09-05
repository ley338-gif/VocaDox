"""Pydantic schemas for the Phase 7 Admin Portal's Dashboard/Models/Jobs/
Workers/Storage/Retention/About surfaces. Provider status response models
(speech/diarization) predate this file — see `app.administration.router`'s
existing `SpeechProviderStatusResponse`/`DiarizationProviderStatusResponse`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    """One dependency's real, live-checked status — never a fabricated
    "Healthy" placeholder (spec §49's hard rule, carried forward from
    Phase 3's provider-vs-platform-readiness distinction, ADR-0023)."""

    name: str
    healthy: bool
    detail: str | None = None


class QueueCounts(BaseModel):
    queued: int
    running: int
    failed: int


class HardwareStatus(BaseModel):
    """Narrow, best-effort hardware snapshot (spec §49: CPU/RAM/GPU/VRAM/
    Disk "where reliably obtainable") — reuses Phase 3's existing
    `app.providers.device.detect_device_capabilities`, no new hardware-
    inventory system. RAM is None on platforms where it cannot be read
    without adding a new third-party dependency (no `psutil` was added
    this phase — see PHASE_7_VALIDATION_REPORT.md's Known Limitations)."""

    cpu_count: int | None
    total_ram_mb: int | None
    cuda_available: bool
    gpu_device_name: str | None
    total_vram_mb: int | None
    free_vram_mb: int | None


class DashboardResponse(BaseModel):
    components: list[ComponentHealth]
    queue: QueueCounts
    hardware: HardwareStatus
    application_version: str


class LLMProviderStatusResponse(BaseModel):
    provider: str
    model: str
    model_revision: str | None
    installed: bool
    device: str
    structured_output: bool
    detail: str | None


class ModelsOverviewResponse(BaseModel):
    """Aggregates the three provider status checks Phase 3/4 already built
    (`get_speech_provider`/`get_diarization_provider`/`get_llm_provider`)
    into one admin page's worth of data — no new status logic, no model
    install/download code path (that stays the Phase 3.1 `model-manager`
    CLI's job; see `docs/admin/model-management.md`)."""

    speech: dict[str, Any]
    diarization: dict[str, Any]
    llm: LLMProviderStatusResponse


class ProcessingJobResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    job_type: str
    status: str
    progress: int
    attempt: int
    max_attempts: int
    failure_class: str | None
    error_code: str | None
    error_message_safe: str | None
    worker_id: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ProcessingJobListResponse(BaseModel):
    items: list[ProcessingJobResponse]
    total: int
    limit: int
    offset: int


class WorkerRoleStatus(BaseModel):
    """Derived purely from `ProcessingJob` rows (`worker_id`/`status`/
    timestamps) already written by Phase 3's worker processes — no new
    worker-registry table, matching the existing "avoid building a
    hardware inventory platform" scoping precedent."""

    role: str
    job_types: list[str]
    running_jobs: int
    queued_jobs: int
    active_worker_ids: list[str]
    last_activity_at: datetime | None


class WorkersOverviewResponse(BaseModel):
    workers: list[WorkerRoleStatus]


class StorageUsageResponse(BaseModel):
    media_storage_root: str
    media_used_bytes: int
    media_disk_total_bytes: int
    media_disk_free_bytes: int
    model_volume_root: str
    model_volume_used_bytes: int
    model_volume_disk_total_bytes: int
    model_volume_disk_free_bytes: int


class RetentionPolicyResponse(BaseModel):
    id: uuid.UUID
    name: str
    retention_days: int | None
    delete_source_media: bool
    delete_derived_media: bool
    delete_transcript: bool
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RetentionPolicyCreateRequest(BaseModel):
    name: str
    retention_days: int | None = None
    delete_source_media: bool = False
    delete_derived_media: bool = False
    delete_transcript: bool = False
    active: bool = True


class RetentionPolicyUpdateRequest(BaseModel):
    name: str | None = None
    retention_days: int | None = None
    delete_source_media: bool | None = None
    delete_derived_media: bool | None = None
    delete_transcript: bool | None = None
    active: bool | None = None


class AboutResponse(BaseModel):
    application_version: str
    license_summary: dict[str, dict[str, int]]
    third_party_notices_excerpt: str
