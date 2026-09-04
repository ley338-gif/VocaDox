"""Phase 8 admin API: technical/quality/correction analytics, the
Evaluation Lab (model + prompt comparison), and Model Lifecycle
transitions. All under `/admin/...`, integrated into the same Admin
Portal shell Phase 7 built (no disconnected parallel screen)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import EvaluationRunType
from app.analytics.schemas import (
    CorrectionMetricsResponse,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    LifecycleEventResponse,
    LifecycleTransitionRequest,
    ModelComparisonRequest,
    ModelLifecycleResponse,
    PromptComparisonRequest,
    QualityMetricsResponse,
    TechnicalAnalyticsResponse,
)
from app.analytics.service import (
    IncompleteChecklistError,
    InvalidLifecycleTransitionError,
    correction_metrics,
    get_evaluation_run,
    list_evaluation_runs,
    list_lifecycle_events,
    provider_for_model_profile,
    quality_metrics,
    run_model_comparison,
    run_prompt_comparison,
    technical_analytics,
    transition_model_lifecycle,
)
from app.audit.service import record_event
from app.identity.deps import require_csrf, require_permission
from app.identity.models import User
from app.platform.db.session import get_session
from app.profiles.models import ModelProfile
from app.templates.models import PromptVersion

router = APIRouter(prefix="/admin", tags=["analytics"])

_require_analytics_read = require_permission("analytics:read")
_require_evaluation_run = require_permission("evaluation:run")
_require_model_profile_promote = require_permission("model-profile:promote")


# -- Technical / Quality / Correction analytics ------------------------------


@router.get("/analytics/technical", response_model=TechnicalAnalyticsResponse)
async def technical_analytics_endpoint(
    _user: User = Depends(_require_analytics_read),
    db: AsyncSession = Depends(get_session),
    days: int = Query(default=30, ge=1, le=365),
) -> TechnicalAnalyticsResponse:
    return TechnicalAnalyticsResponse(**await technical_analytics(db, days=days))


@router.get("/analytics/quality", response_model=QualityMetricsResponse)
async def quality_metrics_endpoint(
    _user: User = Depends(_require_analytics_read),
    db: AsyncSession = Depends(get_session),
) -> QualityMetricsResponse:
    return QualityMetricsResponse(**await quality_metrics(db))


@router.get("/analytics/corrections", response_model=CorrectionMetricsResponse)
async def correction_metrics_endpoint(
    _user: User = Depends(_require_analytics_read),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=200),
) -> CorrectionMetricsResponse:
    return CorrectionMetricsResponse(**await correction_metrics(db, limit=limit))


# -- Evaluation Lab ------------------------------------------------------


@router.get("/evaluation/runs", response_model=EvaluationRunListResponse)
async def list_evaluation_runs_endpoint(
    _user: User = Depends(_require_analytics_read),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EvaluationRunListResponse:
    runs = await list_evaluation_runs(db, limit=limit, offset=offset)
    return EvaluationRunListResponse(
        items=[EvaluationRunResponse.model_validate(r) for r in runs],
        total=len(runs),
        limit=limit,
        offset=offset,
    )


@router.get("/evaluation/runs/{run_id}", response_model=EvaluationRunResponse)
async def get_evaluation_run_endpoint(
    run_id: uuid.UUID,
    _user: User = Depends(_require_analytics_read),
    db: AsyncSession = Depends(get_session),
) -> EvaluationRunResponse:
    run = await get_evaluation_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="evaluation run not found"
        )
    return EvaluationRunResponse.model_validate(run)


@router.post(
    "/evaluation/model-comparison",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_model_comparison_endpoint(
    payload: ModelComparisonRequest,
    actor: User = Depends(_require_evaluation_run),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> EvaluationRunResponse:
    """Runs the real Evaluation Lab fixture through two `ModelProfile`s'
    actual configured providers (spec §50) — never a mockup table. Both
    subjects must be distinct rows; identical ids are rejected (comparing
    a profile to itself is not a comparison)."""
    if payload.model_profile_id_a == payload.model_profile_id_b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="model_profile_id_a and model_profile_id_b must be different",
        )
    profile_a = await db.get(ModelProfile, payload.model_profile_id_a)
    profile_b = await db.get(ModelProfile, payload.model_profile_id_b)
    if profile_a is None or profile_b is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model profile not found")

    run = await run_model_comparison(
        db,
        profile_a=profile_a,
        profile_b=profile_b,
        actor_user_id=actor.id,
    )
    await record_event(
        db,
        event_type="evaluation_run.completed",
        user_id=actor.id,
        username=actor.username,
        event_metadata={
            "evaluation_run_id": str(run.id),
            "run_type": EvaluationRunType.MODEL_COMPARISON.value,
            "status": run.status,
        },
    )
    await db.commit()
    await db.refresh(run)
    return EvaluationRunResponse.model_validate(run)


@router.post(
    "/evaluation/prompt-comparison",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_prompt_comparison_endpoint(
    payload: PromptComparisonRequest,
    actor: User = Depends(_require_evaluation_run),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> EvaluationRunResponse:
    """Compares two `PromptVersion`s (spec §43's DRAFT/TEST/PUBLISHED/
    RETIRED lifecycle) run against the SAME model profile, isolating the
    prompt as the only variable."""
    if payload.prompt_version_id_a == payload.prompt_version_id_b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt_version_id_a and prompt_version_id_b must be different",
        )
    version_a = await db.get(PromptVersion, payload.prompt_version_id_a)
    version_b = await db.get(PromptVersion, payload.prompt_version_id_b)
    profile = await db.get(ModelProfile, payload.model_profile_id)
    if version_a is None or version_b is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prompt version not found"
        )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model profile not found")

    provider = provider_for_model_profile(profile)
    run = await run_prompt_comparison(
        db,
        prompt_version_a=version_a,
        prompt_version_b=version_b,
        provider=provider,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
        model_label=profile.name,
        actor_user_id=actor.id,
    )
    await record_event(
        db,
        event_type="evaluation_run.completed",
        user_id=actor.id,
        username=actor.username,
        event_metadata={
            "evaluation_run_id": str(run.id),
            "run_type": EvaluationRunType.PROMPT_COMPARISON.value,
            "status": run.status,
        },
    )
    await db.commit()
    await db.refresh(run)
    return EvaluationRunResponse.model_validate(run)


# -- Model Lifecycle ------------------------------------------------------


@router.get("/model-profiles/{model_profile_id}/lifecycle", response_model=ModelLifecycleResponse)
async def get_model_lifecycle_endpoint(
    model_profile_id: uuid.UUID,
    _user: User = Depends(_require_analytics_read),
    db: AsyncSession = Depends(get_session),
) -> ModelLifecycleResponse:
    profile = await db.get(ModelProfile, model_profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model profile not found")
    events = await list_lifecycle_events(db, model_profile_id)
    return ModelLifecycleResponse(
        model_profile_id=profile.id,
        lifecycle_status=profile.lifecycle_status,
        events=[LifecycleEventResponse.model_validate(e) for e in events],
    )


@router.post(
    "/model-profiles/{model_profile_id}/lifecycle-transition",
    response_model=LifecycleEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transition_model_lifecycle_endpoint(
    model_profile_id: uuid.UUID,
    payload: LifecycleTransitionRequest,
    actor: User = Depends(_require_model_profile_promote),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> LifecycleEventResponse:
    """Spec §51: every lifecycle transition — forward promotion OR
    rollback — is exactly this one explicit, permission-gated,
    admin-initiated endpoint call. No cron/background process anywhere in
    this codebase calls `transition_model_lifecycle`."""
    profile = await db.get(ModelProfile, model_profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model profile not found")

    from_status = profile.lifecycle_status
    try:
        event = await transition_model_lifecycle(
            db,
            profile,
            to_status=payload.to_status,
            is_rollback=payload.is_rollback,
            checklist=payload.checklist,
            note=payload.note,
            actor_user_id=actor.id,
        )
    except (InvalidLifecycleTransitionError, IncompleteChecklistError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await record_event(
        db,
        event_type="model_profile.lifecycle_transition",
        user_id=actor.id,
        username=actor.username,
        event_metadata={
            "model_profile_id": str(profile.id),
            "from_status": from_status,
            "to_status": payload.to_status,
            "is_rollback": payload.is_rollback,
        },
    )
    await db.commit()
    await db.refresh(event)
    return LifecycleEventResponse.model_validate(event)
