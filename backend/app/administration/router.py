"""Admin-only provider status endpoints (spec: "Admin provider status
page" / "Provider health vs. platform readiness"). Deliberately separate
from `/health/ready` (app.platform.health) — an AI model not being
installed must never make the platform itself report unready; it's
surfaced here instead, admin-gated, with an honest "not installed" rather
than a fake "Healthy".

Phase 3 config is file/env-based only (Settings) — no provider
configuration UI exists yet (that's Phase 7); these endpoints are
read-only status, not configuration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.ai_providers import get_diarization_provider, get_speech_provider
from app.identity.deps import require_permission
from app.identity.models import User
from app.providers.diarization import DiarizationProvider
from app.providers.speech_to_text import SpeechToTextProvider

router = APIRouter(prefix="/admin/providers", tags=["administration"])

# Module-level singleton dependency (not called inline in a Depends()
# default, per the codebase's lint policy against B008).
_require_provider_read = require_permission("provider:read")


class SpeechProviderStatusResponse(BaseModel):
    provider: str
    model: str
    model_revision: str | None
    installed: bool
    device: str
    cuda_available: bool
    detail: str | None


class DiarizationProviderStatusResponse(BaseModel):
    provider: str
    model: str
    model_revision: str | None
    installed: bool
    detail: str | None


@router.get("/speech", response_model=SpeechProviderStatusResponse)
async def speech_provider_status_endpoint(
    _user: User = Depends(_require_provider_read),
    speech_provider: SpeechToTextProvider = Depends(get_speech_provider),
) -> SpeechProviderStatusResponse:
    status_ = speech_provider.status()
    return SpeechProviderStatusResponse(
        provider=status_.provider,
        model=status_.model,
        model_revision=status_.model_revision,
        installed=status_.installed,
        device=status_.device,
        cuda_available=status_.cuda_available,
        detail=status_.detail,
    )


@router.get("/diarization", response_model=DiarizationProviderStatusResponse)
async def diarization_provider_status_endpoint(
    _user: User = Depends(_require_provider_read),
    diarization_provider: DiarizationProvider = Depends(get_diarization_provider),
) -> DiarizationProviderStatusResponse:
    status_ = diarization_provider.status()
    return DiarizationProviderStatusResponse(
        provider=status_.provider,
        model=status_.model,
        model_revision=status_.model_revision,
        installed=status_.installed,
        detail=status_.detail,
    )
