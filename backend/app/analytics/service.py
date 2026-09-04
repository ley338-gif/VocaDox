"""Phase 8 analytics/evaluation/model-lifecycle business logic.

Technical/quality/correction analytics are honest, real, descriptive
statistics computed directly from Phase 3/4/5 tables that already exist
(`processing_jobs`, `transcript_segments`/`transcript_segment_corrections`,
`extracted_facts`/`fact_corrections`, `review_issues`) — never a
fabricated "AI accuracy" number. Every metric here has a precise,
documented definition (see each function's docstring) rather than an
unexplained percentage.

Model Lifecycle (spec §51) enforcement: the five-step "model update"
checklist (License Check / Compatibility Check / Benchmark / Security
Review / Admin Approval) is recorded as an admin-attested boolean bag on
every FORWARD transition — this code cannot itself verify a license was
actually checked or a benchmark actually run, so it enforces that the
admin explicitly asserts each step happened (structural enforcement of
the *process*, not automated verification of its *content*). Rollback
transitions skip the checklist (a rollback is itself the safety
mechanism, never a promotion) but are still always an explicit,
audited admin action — there is no code path in this file, or anywhere
else in this codebase, that changes `lifecycle_status` without an admin
calling `transition_model_lifecycle` directly.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.eval_engine import EvalSubject, run_eval_subject
from app.analytics.fixtures import FIXTURE_KEY
from app.analytics.models import EvaluationRun, EvaluationRunType, ModelProfileLifecycleEvent
from app.core.ai_providers import get_llm_provider_for_model_identifier
from app.intelligence.models import ExtractedFact, FactCorrection, FactReviewStatus
from app.intelligence.prompts import SYSTEM_PROMPT, get_builtin_category_instruction
from app.intelligence.schemas import EXTRACTION_CATEGORIES
from app.processing.models import JobType, ProcessingJob, ProcessingStatus
from app.profiles.models import ModelLifecycleStatus, ModelProfile
from app.providers.llm import LLMProvider
from app.review.models import ReviewIssue
from app.templates.models import PromptVersion
from app.transcription.models import TranscriptSegment, TranscriptSegmentCorrection


def _builtin_category_instructions() -> dict[str, str]:
    return {
        category: get_builtin_category_instruction(category) for category in EXTRACTION_CATEGORIES
    }


def provider_for_model_profile(profile: ModelProfile) -> LLMProvider:
    """Builds a real provider instance for a specific `ModelProfile` row
    via the cross-cutting `app.core.ai_providers` factory (domain code must
    never construct a concrete provider implementation directly — see
    tests/test_architecture_boundaries.py) — needed so the Evaluation Lab
    can run two DIFFERENT profiles concurrently, whereas
    `get_llm_provider` only ever builds the single globally-configured
    provider."""
    return get_llm_provider_for_model_identifier(
        provider=profile.provider, model_identifier=profile.model_identifier
    )


# -- Technical analytics ------------------------------------------------------


async def technical_analytics(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """Real operational metrics over `ProcessingJob` rows (Phase 3) —
    reuses the exact same data source as Phase 7's admin Jobs/Workers
    views, no duplicate job-tracking table. Response is structurally
    counts/labels/floats only — never a conversation id's content, only
    its id (and only inside per-job-type aggregate counts, not a list of
    individual conversations).

    Definitions:
    - `volume_by_day`: count of jobs QUEUED per calendar day (job's
      `queued_at`, UTC), for the last `days` days.
    - `by_job_type[type].success_rate`: succeeded / (succeeded + failed)
      among that type's terminally-finished jobs (cancelled excluded from
      the denominator — cancellation isn't a quality signal). `None` when
      there are zero terminal jobs of that type yet.
    - `by_job_type[type].avg_latency_seconds`: mean of
      (completed_at - started_at) over that type's SUCCEEDED jobs with
      both timestamps set. `None` when there are none.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(select(ProcessingJob).where(ProcessingJob.queued_at >= cutoff))
    jobs = list(result.scalars().all())

    volume_by_day: Counter[str] = Counter()
    by_type: dict[str, dict[str, Any]] = {
        jt.value: {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0}
        for jt in JobType
    }
    latencies_by_type: dict[str, list[float]] = defaultdict(list)

    for job in jobs:
        day_key = job.queued_at.date().isoformat()
        volume_by_day[day_key] += 1
        counts = by_type.setdefault(
            job.job_type, {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0}
        )
        if job.status in counts:
            counts[job.status] += 1
        if (
            job.status == ProcessingStatus.SUCCEEDED.value
            and job.started_at is not None
            and job.completed_at is not None
        ):
            latencies_by_type[job.job_type].append(
                (job.completed_at - job.started_at).total_seconds()
            )

    by_job_type: dict[str, dict[str, Any]] = {}
    for job_type, counts in by_type.items():
        terminal = counts["succeeded"] + counts["failed"]
        success_rate = (counts["succeeded"] / terminal) if terminal else None
        latencies = latencies_by_type.get(job_type, [])
        avg_latency = (sum(latencies) / len(latencies)) if latencies else None
        by_job_type[job_type] = {
            **counts,
            "success_rate": success_rate,
            "avg_latency_seconds": avg_latency,
        }

    return {
        "window_days": days,
        "total_jobs": len(jobs),
        "volume_by_day": dict(sorted(volume_by_day.items())),
        "by_job_type": by_job_type,
    }


# -- Quality metrics ------------------------------------------------------


async def quality_metrics(db: AsyncSession) -> dict[str, Any]:
    """Honest, precisely-defined descriptive statistics over real
    correction/review data (Phase 3/4/5) — never a fabricated "accuracy"
    figure without a defined methodology.

    - `transcript_correction_rate`: (distinct `transcript_segments` with
      at least one `transcript_segment_corrections` row) / (total
      `transcript_segments`). Measures "how often ASR output gets
      corrected by a human", nothing more.
    - `fact_review_status_counts` / `fact_corrected_or_removed_rate`:
      counts of `extracted_facts.review_status`, and
      (corrected + removed) / total. Measures "how often an extracted
      fact is later corrected or removed during review" — NOT "AI
      accuracy": a fact reviewed as CONFIRMED could still be wrong if no
      reviewer caught it, and PENDING facts haven't been reviewed at all
      yet, both real, disclosed limitations of this metric.
    - `review_issue_resolution_counts`: counts of `review_issues.status`
      and, among resolved ones, `resolved_status` (confirmed/corrected/
      removed) — how review-flagged issues actually get resolved.
    """
    total_segments = (
        await db.execute(select(func.count()).select_from(TranscriptSegment))
    ).scalar_one()
    corrected_segments = (
        await db.execute(
            select(func.count(func.distinct(TranscriptSegmentCorrection.segment_id)))
        )
    ).scalar_one()
    transcript_correction_rate = (
        (corrected_segments / total_segments) if total_segments else None
    )

    fact_rows = (
        await db.execute(select(ExtractedFact.review_status, func.count()).group_by(
            ExtractedFact.review_status
        ))
    ).all()
    fact_review_status_counts = {status: count for status, count in fact_rows}
    total_facts = sum(fact_review_status_counts.values())
    corrected_or_removed = fact_review_status_counts.get(
        FactReviewStatus.CORRECTED.value, 0
    ) + fact_review_status_counts.get(FactReviewStatus.REMOVED.value, 0)
    fact_corrected_or_removed_rate = (corrected_or_removed / total_facts) if total_facts else None

    issue_status_rows = (
        await db.execute(select(ReviewIssue.status, func.count()).group_by(ReviewIssue.status))
    ).all()
    resolved_status_rows = (
        await db.execute(
            select(ReviewIssue.resolved_status, func.count())
            .where(ReviewIssue.resolved_status.is_not(None))
            .group_by(ReviewIssue.resolved_status)
        )
    ).all()

    return {
        "transcript_segments_total": total_segments,
        "transcript_segments_corrected": corrected_segments,
        "transcript_correction_rate": transcript_correction_rate,
        "fact_review_status_counts": fact_review_status_counts,
        "facts_total": total_facts,
        "fact_corrected_or_removed_rate": fact_corrected_or_removed_rate,
        "review_issue_status_counts": {status: count for status, count in issue_status_rows},
        "review_issue_resolution_counts": {
            status: count for status, count in resolved_status_rows
        },
    }


# -- Correction metrics ------------------------------------------------------


async def correction_metrics(db: AsyncSession, *, limit: int = 20) -> dict[str, Any]:
    """Real, queryable analytics over the correction-feedback audit trails
    that have existed since Phase 3 (`transcript_segment_corrections`) and
    Phase 5 (`fact_corrections`) — genuinely useful for admins/template
    designers, per spec §38 explicitly NOT a training pipeline: this
    module only ever reads these tables to compute counts, it never feeds
    them into a model-training code path (none exists anywhere in this
    codebase).

    - `fact_corrections_by_category`: correction-event count grouped by
      the corrected fact's `category` (general_fact/decision/task).
    - `most_corrected_subjects`: for GENERAL_FACT corrections specifically,
      the `subject` field (e.g. "Ramipril") of `new_structured_value`,
      counted — the closest honest reading of "most-corrected terms" the
      real schema supports (subject/attribute/value triples have no
      separate "term" field).
    - `transcript_segment_corrections_total`: total correction-event count
      (Phase 3 data).
    """
    fact_corr_rows = (
        await db.execute(
            select(ExtractedFact.category, func.count())
            .join(FactCorrection, FactCorrection.fact_id == ExtractedFact.id)
            .group_by(ExtractedFact.category)
        )
    ).all()

    general_fact_corrections = (
        await db.execute(
            select(FactCorrection.new_structured_value)
            .join(ExtractedFact, ExtractedFact.id == FactCorrection.fact_id)
            .where(ExtractedFact.category == "general_fact")
        )
    ).scalars().all()
    subject_counter: Counter[str] = Counter()
    for value in general_fact_corrections:
        subject = (value or {}).get("subject")
        if isinstance(subject, str) and subject:
            subject_counter[subject] += 1
    most_corrected_subjects = [
        {"subject": subject, "count": count}
        for subject, count in subject_counter.most_common(limit)
    ]

    segment_corrections_total = (
        await db.execute(select(func.count()).select_from(TranscriptSegmentCorrection))
    ).scalar_one()

    return {
        "fact_corrections_by_category": {category: count for category, count in fact_corr_rows},
        "most_corrected_subjects": most_corrected_subjects,
        "transcript_segment_corrections_total": segment_corrections_total,
    }


# -- Evaluation Lab ------------------------------------------------------


async def run_model_comparison(
    db: AsyncSession,
    *,
    profile_a: ModelProfile,
    profile_b: ModelProfile,
    actor_user_id: uuid.UUID | None,
) -> EvaluationRun:
    """Runs the fixture (app.analytics.fixtures) through both `profile_a`
    and `profile_b`'s own provider/model config, using the exact same
    built-in system prompt/category instructions
    (app.intelligence.prompts) for both — isolating the model as the only
    variable, matching a real model-vs-model comparison's actual purpose."""
    run = EvaluationRun(
        run_type=EvaluationRunType.MODEL_COMPARISON.value,
        fixture_key=FIXTURE_KEY,
        subject_a=_model_profile_subject_dict(profile_a),
        subject_b=_model_profile_subject_dict(profile_b),
    )
    db.add(run)
    await db.flush()

    category_instructions = _builtin_category_instructions()
    try:
        result_a = await run_eval_subject(
            EvalSubject(
                label=profile_a.name,
                provider=provider_for_model_profile(profile_a),
                temperature=profile_a.temperature,
                max_tokens=profile_a.max_tokens,
                system_prompt=SYSTEM_PROMPT,
                category_instructions=category_instructions,
            )
        )
        result_b = await run_eval_subject(
            EvalSubject(
                label=profile_b.name,
                provider=provider_for_model_profile(profile_b),
                temperature=profile_b.temperature,
                max_tokens=profile_b.max_tokens,
                system_prompt=SYSTEM_PROMPT,
                category_instructions=category_instructions,
            )
        )
        run.result_a = result_a.as_public_dict()
        run.result_b = result_b.as_public_dict()
        run.status = "completed"
    except Exception as exc:  # noqa: BLE001 - a failed comparison must be visible, not raised
        run.status = "failed"
        run.error_message_safe = f"{type(exc).__name__}: {exc}"[:1000]
    run.created_by_user_id = actor_user_id
    run.completed_at = datetime.now(UTC)
    await db.flush()
    return run


async def run_prompt_comparison(
    db: AsyncSession,
    *,
    prompt_version_a: PromptVersion,
    prompt_version_b: PromptVersion,
    provider: LLMProvider,
    temperature: float,
    max_tokens: int,
    model_label: str,
    actor_user_id: uuid.UUID | None,
) -> EvaluationRun:
    """Runs the fixture through the SAME provider/model config for both
    prompt versions — isolating the prompt as the only variable."""
    run = EvaluationRun(
        run_type=EvaluationRunType.PROMPT_COMPARISON.value,
        fixture_key=FIXTURE_KEY,
        subject_a=_prompt_version_subject_dict(prompt_version_a, model_label=model_label),
        subject_b=_prompt_version_subject_dict(prompt_version_b, model_label=model_label),
    )
    db.add(run)
    await db.flush()

    try:
        result_a = await run_eval_subject(
            EvalSubject(
                label=f"prompt v{prompt_version_a.version_number}",
                provider=provider,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=prompt_version_a.system_prompt,
                category_instructions=prompt_version_a.category_instructions,
            )
        )
        result_b = await run_eval_subject(
            EvalSubject(
                label=f"prompt v{prompt_version_b.version_number}",
                provider=provider,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=prompt_version_b.system_prompt,
                category_instructions=prompt_version_b.category_instructions,
            )
        )
        run.result_a = result_a.as_public_dict()
        run.result_b = result_b.as_public_dict()
        run.status = "completed"
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message_safe = f"{type(exc).__name__}: {exc}"[:1000]
    run.created_by_user_id = actor_user_id
    run.completed_at = datetime.now(UTC)
    await db.flush()
    return run


def _model_profile_subject_dict(profile: ModelProfile) -> dict[str, Any]:
    return {
        "kind": "model_profile",
        "id": str(profile.id),
        "name": profile.name,
        "provider": profile.provider,
        "model_identifier": profile.model_identifier,
        "temperature": profile.temperature,
        "max_tokens": profile.max_tokens,
    }


def _prompt_version_subject_dict(version: PromptVersion, *, model_label: str) -> dict[str, Any]:
    return {
        "kind": "prompt_version",
        "id": str(version.id),
        "prompt_id": str(version.prompt_id),
        "version_number": version.version_number,
        "status": version.status,
        "model_label": model_label,
    }


async def get_evaluation_run(db: AsyncSession, run_id: uuid.UUID) -> EvaluationRun | None:
    return await db.get(EvaluationRun, run_id)


async def list_evaluation_runs(
    db: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[EvaluationRun]:
    result = await db.execute(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


# -- Model Lifecycle ------------------------------------------------------

_LIFECYCLE_ORDER: list[str] = [
    ModelLifecycleStatus.AVAILABLE.value,
    ModelLifecycleStatus.TESTING.value,
    ModelLifecycleStatus.PILOT.value,
    ModelLifecycleStatus.PRODUCTION.value,
    ModelLifecycleStatus.RETIRED.value,
]

_REQUIRED_CHECKLIST_KEYS = (
    "license_check",
    "compatibility_check",
    "benchmark",
    "security_review",
    "admin_approval",
)


class InvalidLifecycleTransitionError(ValueError):
    pass


class IncompleteChecklistError(ValueError):
    pass


async def transition_model_lifecycle(
    db: AsyncSession,
    profile: ModelProfile,
    *,
    to_status: str,
    is_rollback: bool,
    checklist: dict[str, Any] | None,
    note: str | None,
    actor_user_id: uuid.UUID | None,
) -> ModelProfileLifecycleEvent:
    """Spec §51: every transition (forward OR rollback) is an explicit
    admin action recorded here — no automatic/unattended caller exists
    anywhere in this codebase. See module docstring for the checklist
    enforcement rationale."""
    if to_status not in _LIFECYCLE_ORDER:
        raise InvalidLifecycleTransitionError(f"unknown lifecycle status: {to_status!r}")

    from_status = profile.lifecycle_status
    from_index = _LIFECYCLE_ORDER.index(from_status)
    to_index = _LIFECYCLE_ORDER.index(to_status)

    if is_rollback:
        if to_index >= from_index:
            raise InvalidLifecycleTransitionError(
                f"rollback must move to an EARLIER status than {from_status!r}, got {to_status!r}"
            )
    else:
        if to_index != from_index + 1:
            raise InvalidLifecycleTransitionError(
                f"cannot advance from {from_status!r} directly to {to_status!r} — lifecycle "
                f"transitions move exactly one step forward at a time "
                f"({' -> '.join(_LIFECYCLE_ORDER)}), or set is_rollback=true to move backward"
            )
        checklist = checklist or {}
        missing = [key for key in _REQUIRED_CHECKLIST_KEYS if not checklist.get(key)]
        if missing:
            raise IncompleteChecklistError(
                "model update checklist incomplete, missing/false: " + ", ".join(missing)
            )

    profile.lifecycle_status = to_status
    event = ModelProfileLifecycleEvent(
        model_profile_id=profile.id,
        from_status=from_status,
        to_status=to_status,
        is_rollback=is_rollback,
        checklist=checklist,
        note=note,
        actor_user_id=actor_user_id,
    )
    db.add(event)
    await db.flush()
    return event


async def list_lifecycle_events(
    db: AsyncSession, model_profile_id: uuid.UUID
) -> list[ModelProfileLifecycleEvent]:
    result = await db.execute(
        select(ModelProfileLifecycleEvent)
        .where(ModelProfileLifecycleEvent.model_profile_id == model_profile_id)
        .order_by(ModelProfileLifecycleEvent.created_at.asc())
    )
    return list(result.scalars().all())
