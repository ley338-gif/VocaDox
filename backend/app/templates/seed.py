"""Idempotent bootstrap for Phase 6's initial templates/prompts — mirrors
`app.identity.seed`/`app.profiles.seed`'s pattern exactly (safe to call on
every startup, only inserts rows that don't already exist by `key`).

Seeds, per spec §42's Phase 6 scope:
  - **general** (published v1) — the exact 3 builtin categories
    (general_fact/decision/task) Phase 4/5 already hardcoded, so
    extraction/composition behavior for any conversation using this
    template (including every pre-Phase-6 conversation, via the
    SYSTEM DEFAULT fallback — see app.profiles.resolver) is unchanged.
  - **meeting** (published v1) — genuinely different fields/categories
    (agenda_topic/decision-with-rationale/action_item-with-owner), proving
    the Template Engine actually drives different extraction behavior, not
    a renamed copy of general.
  - **medical_consultation** (published, post-GA) — five categories
    (Anamnese/Befund/Diagnose/Therapie/Prozedere-Empfehlung — Befund and
    Prozedere/Empfehlung are genuinely separate from Anamnese and
    Therapie respectively, not folded in, so both a Krankenblatt-style
    chart note and a real Arztbrief have somewhere to put examiner
    findings and follow-up plans), composed with `document_layout="letter"`
    (a formal Arztbrief: Betreff, Anrede, the five sections above as prose
    paragraphs instead of bullets, Grußformel — see
    app.documents.service.compose_document and
    app.documents.export_formats) instead of the generic flat-section
    layout every other template uses.
  - **psychotherapy** (DRAFT only, never published) — data-model-ready
    foundation per the brief ("prepared... not necessarily fully
    field-complete... do not over-engineer"). Being left unpublished
    means no ProcessingProfile can reference it yet
    (`get_published_version` raises) — a deliberate, honest signal that
    it is not a real, selectable option in this phase.

A matching Prompt/PromptVersion is seeded per template's extraction
categories (spec §43) so `ProcessingRun.prompt_version_id` has something
real to reference from the very first extraction run.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.prompts import SYSTEM_PROMPT, get_builtin_category_instruction
from app.templates.models import PromptVersion, TemplateVersion
from app.templates.service import (
    create_draft_prompt_version,
    create_draft_version,
    create_prompt,
    create_template,
    get_prompt_by_key,
    get_template_by_key,
    list_prompt_versions,
    list_template_versions,
    publish_prompt_version,
    publish_template_version,
)

_GENERAL_CATEGORIES = [
    {"key": "general_fact", "builtin": True},
    {"key": "decision", "builtin": True},
    {"key": "task", "builtin": True},
]
_GENERAL_PRESENTATION = [
    {"category": "general_fact", "title": "General Facts"},
    {"category": "decision", "title": "Decisions"},
    {"category": "task", "title": "Tasks & Follow-Ups"},
]

_MEETING_CATEGORIES = [
    {
        "key": "agenda_topic",
        "fact_type": "agenda_topic",
        "item_field": "topics",
        "instruction": (
            "Extract each distinct agenda topic/subject that was actually discussed in this "
            "meeting. For each, summarize what was discussed and note the outcome/conclusion if "
            "one was reached, otherwise 'NOT_MENTIONED'."
        ),
        "fields": [
            {"name": "topic", "max_length": 256, "description": "Short topic name."},
            {"name": "summary", "max_length": 1024, "description": "What was discussed."},
            {
                "name": "outcome",
                "max_length": 256,
                "description": "Conclusion reached, or 'NOT_MENTIONED'.",
            },
        ],
    },
    {
        "key": "decision",
        "fact_type": "decision",
        "item_field": "decisions",
        "instruction": (
            "Extract concrete decisions made during this meeting (not proposals or open "
            "questions). For each, note who decided it — using the speaker label for the "
            "line where they made it — and the stated rationale/reasoning if any, otherwise "
            "'NOT_MENTIONED' for either field."
        ),
        "fields": [
            {"name": "description", "max_length": 1024},
            {
                "name": "decided_by",
                "max_length": 256,
                "description": "Person/role, or 'NOT_MENTIONED'.",
            },
            {
                "name": "rationale",
                "max_length": 512,
                "description": "Why this decision was made, or 'NOT_MENTIONED'.",
            },
        ],
    },
    {
        "key": "action_item",
        "fact_type": "action_item",
        "item_field": "action_items",
        "instruction": (
            "Extract concrete action items with a clear owner that someone committed to doing "
            "after this meeting. For each, note the owner — using the speaker label for the "
            "line where they committed to it — due date, and priority if stated, using "
            "'NOT_MENTIONED' for any field that wasn't. Capture the due date exactly as "
            "spoken, including relative or informal time references (e.g. 'tomorrow morning', "
            "'by end of week', 'next Monday', 'morgen Vormittag') — a relative phrase still "
            "counts as stated; only use 'NOT_MENTIONED' if no time reference was said at all. "
            "If a speaker commits to doing something themselves (e.g. 'I can take care of "
            "that', 'I'll do it', 'ich kann das übernehmen'), record their speaker label as "
            "the owner even though they only referred to themselves in the first person, not "
            "by name."
        ),
        "fields": [
            {"name": "description", "max_length": 1024},
            {
                "name": "owner",
                "max_length": 256,
                "description": "Person/role responsible, or 'NOT_MENTIONED'.",
            },
            {
                "name": "due_date",
                "max_length": 128,
                "description": "Date/time phrase, or 'NOT_MENTIONED'.",
            },
            {
                "name": "priority",
                "max_length": 64,
                "description": "e.g. 'high', or 'NOT_MENTIONED'.",
            },
        ],
    },
]
_MEETING_PRESENTATION = [
    {"category": "agenda_topic", "title": "Agenda & Discussion"},
    {"category": "decision", "title": "Decisions"},
    {"category": "action_item", "title": "Action Items"},
]

# Post-GA, published — see module docstring. Five categories map onto a
# classic Arztbrief/Krankenblatt structure: Anamnese (patient-reported),
# Befund (examiner-observed, kept separate from Anamnese since the two
# have different evidentiary weight in a real chart note), Diagnose,
# Therapie (medication), and Prozedere/Empfehlung (follow-up plan/next
# steps — deliberately its own category, not folded into medication,
# since a recommendation like "erneut untersuchen in zwei Wochen" or a
# warning sign to watch for is not a medication).
_MEDICAL_CATEGORIES = [
    {
        "key": "symptom",
        "fact_type": "symptom",
        "item_field": "symptoms",
        "instruction": "Extract symptoms the patient reported, with onset and severity if stated.",
        "fields": [
            {"name": "description", "max_length": 512},
            {"name": "onset", "max_length": 128, "description": "'NOT_MENTIONED' if not stated."},
            {"name": "severity", "max_length": 64, "description": "'NOT_MENTIONED' if not stated."},
        ],
    },
    {
        "key": "finding",
        "fact_type": "finding",
        "item_field": "findings",
        "instruction": (
            "Extract objective examination findings explicitly stated by the examiner "
            "(e.g. auscultation, vital signs, test/measurement results) -- not symptoms the "
            "patient reported about themselves, which is a separate category. For each, note "
            "the finding and its result/value."
        ),
        "fields": [
            {"name": "description", "max_length": 512},
            {
                "name": "result",
                "max_length": 256,
                "description": "The observed value/result, or 'NOT_MENTIONED' if not stated.",
            },
        ],
    },
    {
        "key": "medication",
        "fact_type": "medication",
        "item_field": "medications",
        "instruction": "Extract medications discussed, with dose/frequency if stated.",
        "fields": [
            {"name": "name", "max_length": 256},
            {"name": "dose", "max_length": 128, "description": "'NOT_MENTIONED' if not stated."},
            {
                "name": "frequency",
                "max_length": 128,
                "description": "'NOT_MENTIONED' if not stated.",
            },
        ],
    },
    {
        "key": "diagnosis",
        "fact_type": "diagnosis",
        "item_field": "diagnoses",
        "instruction": "Extract diagnoses explicitly stated during the consultation.",
        "fields": [{"name": "description", "max_length": 512}],
    },
    {
        "key": "recommendation",
        "fact_type": "recommendation",
        "item_field": "recommendations",
        "instruction": (
            "Extract recommendations, follow-up plans, or warning signs the clinician "
            "communicated to the patient -- e.g. further tests, a follow-up appointment, or "
            "when to seek care again -- but NOT medications, which are a separate category. "
            "For each, note the timeframe if one was given."
        ),
        "fields": [
            {"name": "description", "max_length": 512},
            {
                "name": "timeframe",
                "max_length": 128,
                "description": "'NOT_MENTIONED' if not stated.",
            },
        ],
    },
]
_MEDICAL_PRESENTATION = [
    {"category": "symptom", "title": "Anamnese"},
    {"category": "finding", "title": "Befund"},
    {"category": "diagnosis", "title": "Diagnose"},
    {"category": "medication", "title": "Therapie"},
    {"category": "recommendation", "title": "Prozedere / Empfehlung"},
]

_PSYCHOTHERAPY_CATEGORIES = [
    {
        "key": "theme",
        "fact_type": "theme",
        "item_field": "themes",
        "instruction": "Extract themes/topics the client raised during the session.",
        "fields": [{"name": "description", "max_length": 512}],
    },
    {
        "key": "intervention",
        "fact_type": "intervention",
        "item_field": "interventions",
        "instruction": "Extract therapeutic interventions/techniques the therapist applied.",
        "fields": [{"name": "description", "max_length": 512}],
    },
    {
        "key": "goal",
        "fact_type": "goal",
        "item_field": "goals",
        "instruction": "Extract treatment goals discussed and their stated status.",
        "fields": [
            {"name": "description", "max_length": 512},
            {"name": "status", "max_length": 64, "description": "'NOT_MENTIONED' if not stated."},
        ],
    },
]
_PSYCHOTHERAPY_PRESENTATION = [
    {"category": "theme", "title": "Themes"},
    {"category": "intervention", "title": "Interventions"},
    {"category": "goal", "title": "Goals"},
]


async def apply_seed(session: AsyncSession) -> None:
    await _seed_template(
        session,
        key="general",
        name="General Conversation",
        description=(
            "Domain-neutral extraction: general facts, decisions, tasks/follow-ups. Identical "
            "categories to Phase 4/5's hardcoded default — the SYSTEM DEFAULT fallback."
        ),
        categories=_GENERAL_CATEGORIES,
        presentation=_GENERAL_PRESENTATION,
        publish=True,
    )
    await _seed_template(
        session,
        key="meeting",
        name="Meeting",
        description="Agenda topics, decisions with rationale, action items with owner/due date.",
        categories=_MEETING_CATEGORIES,
        presentation=_MEETING_PRESENTATION,
        publish=True,
    )
    await _seed_template(
        session,
        key="medical_consultation",
        name="Medical Consultation",
        description=(
            "Anamnese/Befund/Diagnose/Therapie/Prozedere-Extraktion, komponiert als formaler "
            "Arztbrief (Betreff, Anamnese, Befund, Diagnose, Therapie, Prozedere/Empfehlung) "
            "statt der generischen Abschnitts-Ansicht — post-GA, wählbar über ein "
            "Verarbeitungsprofil."
        ),
        categories=_MEDICAL_CATEGORIES,
        presentation=_MEDICAL_PRESENTATION,
        publish=True,
        document_layout="letter",
    )
    await _seed_template(
        session,
        key="psychotherapy",
        name="Psychotherapy",
        description="Foundation only (spec §42) — data-model-ready, not published/selectable yet.",
        categories=_PSYCHOTHERAPY_CATEGORIES,
        presentation=_PSYCHOTHERAPY_PRESENTATION,
        publish=False,
    )


async def _seed_template(
    session: AsyncSession,
    *,
    key: str,
    name: str,
    description: str,
    categories: list[dict],
    presentation: list[dict],
    publish: bool,
    document_layout: str = "sections",
) -> None:
    instructions = {
        c["key"]: (
            get_builtin_category_instruction(c["key"]) if c.get("builtin") else c["instruction"]
        )
        for c in categories
    }
    prompt_key = f"extraction-{key}"

    existing = await get_template_by_key(session, key)
    if existing is not None:
        # The template/categories/presentation themselves are immutable
        # once created (a real content change there needs a new Template
        # Version through the Admin Portal, like any other). But the
        # extraction PROMPT wording is source-controlled here and DOES need
        # a way to actually reach an already-seeded install: re-running
        # this seed (`python -m app.templates.seed`, same idempotent
        # "safe on every startup" pattern as app.identity.seed) detects
        # when the currently-published PromptVersion's content has drifted
        # from these source constants and publishes a fresh version — the
        # same create-draft-then-publish flow the Admin Portal itself uses
        # — so a prompt wording fix (like this one) actually changes
        # extraction behavior instead of only affecting brand new installs.
        if publish:
            versions = await list_template_versions(session, existing.id)
            current = (
                await session.get(TemplateVersion, existing.current_published_version_id)
                if existing.current_published_version_id is not None
                else None
            )
            # Two cases share one fix: (a) a template previously seeded
            # DRAFT-only (medical_consultation before this change) that is
            # now meant to be a real, selectable option, and (b) a template
            # that WAS already published in some environments with a
            # STALE version (e.g. medical_consultation published directly
            # via the Admin Portal before it gained a letter layout/German
            # titles here). Both need a fresh DRAFT version carrying
            # today's source content, published over the stale one — same
            # create-then-publish flow the Admin Portal itself uses, never
            # mutating any existing version's content in place.
            drifted = current is None or (
                current.presentation != presentation
                or current.extraction_categories != categories
                or current.document_layout != document_layout
            )
            if drifted:
                new_version = await create_draft_version(
                    session,
                    template=existing,
                    extraction_categories=categories,
                    presentation=presentation,
                    review_rules=versions[-1].review_rules if versions else None,
                    document_layout=document_layout,
                    created_by=None,  # type: ignore[arg-type]
                )
                await publish_template_version(
                    session, template=existing, version=new_version, published_by=None
                )
            # Foundation-only templates (publish=False — psychotherapy) keep
            # their prompt DRAFT and untouched by any of this, exactly as
            # `_seed_template`'s create path already does — "not yet a real,
            # selectable option" per spec §42 is a deliberate, standing
            # state, not something an unrelated wording fix elsewhere
            # should silently publish.
            await _republish_prompt_if_drifted(
                session,
                prompt_key=prompt_key,
                system_prompt=SYSTEM_PROMPT,
                instructions=instructions,
            )
        return

    template = await create_template(
        session,
        key=key,
        name=name,
        description=description,
        extraction_categories=categories,
        presentation=presentation,
        review_rules=None,
        document_layout=document_layout,
        created_by=None,  # type: ignore[arg-type]
    )
    if await get_prompt_by_key(session, prompt_key) is None:
        await create_prompt(
            session,
            key=prompt_key,
            name=f"{name} Extraction Prompt",
            purpose="extraction",
            system_prompt=SYSTEM_PROMPT,
            category_instructions=instructions,
            created_by=None,
        )

    if publish:
        versions = await list_template_versions(session, template.id)
        await publish_template_version(
            session, template=template, version=versions[0], published_by=None
        )

        prompt = await get_prompt_by_key(session, prompt_key)
        if prompt is not None and prompt.current_published_version_id is None:
            prompt_versions = await list_prompt_versions(session, prompt.id)
            await publish_prompt_version(
                session, prompt=prompt, version=prompt_versions[0], published_by=None
            )


async def _republish_prompt_if_drifted(
    session: AsyncSession,
    *,
    prompt_key: str,
    system_prompt: str,
    instructions: dict[str, str],
) -> None:
    prompt = await get_prompt_by_key(session, prompt_key)
    if prompt is None:
        return  # a DRAFT-only (unpublished) template's prompt; nothing to drift-check yet
    current = (
        await session.get(PromptVersion, prompt.current_published_version_id)
        if prompt.current_published_version_id is not None
        else None
    )
    if (
        current is not None
        and current.system_prompt == system_prompt
        and current.category_instructions == instructions
    ):
        return
    new_version = await create_draft_prompt_version(
        session,
        prompt=prompt,
        system_prompt=system_prompt,
        category_instructions=instructions,
        created_by=None,  # type: ignore[arg-type]
    )
    await publish_prompt_version(session, prompt=prompt, version=new_version, published_by=None)


async def _reseed_cli() -> int:  # pragma: no cover - trivial CLI wrapper
    from app.platform.db import model_registry  # noqa: F401
    from app.platform.db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await apply_seed(session)
        await session.commit()
    print("Template/prompt seed applied (created if none existed, prompts republished if changed).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    raise SystemExit(asyncio.run(_reseed_cli()))
