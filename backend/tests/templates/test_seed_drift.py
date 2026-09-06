"""`app.templates.seed.apply_seed` is safe to run on every startup/deploy
(mirrors `app.identity.seed`) — this covers the part that's easy to get
wrong: an already-seeded install must pick up a real prompt wording change
(e.g. the speaker-attribution fix) by publishing a NEW PromptVersion,
never by silently doing nothing just because the Template/Prompt rows
already exist.
"""

from __future__ import annotations

from app.templates.models import PromptVersion, VersionLifecycleStatus
from app.templates.seed import apply_seed
from app.templates.service import get_prompt_by_key
from sqlalchemy import select


async def test_reseeding_with_unchanged_source_is_a_true_no_op(app_env) -> None:  # noqa: ANN001
    _, sessionmaker = app_env
    async with sessionmaker() as session:
        await apply_seed(session)
        await session.commit()

    async with sessionmaker() as session:
        prompt = await get_prompt_by_key(session, "extraction-meeting")
        assert prompt is not None
        published_version_id_before = prompt.current_published_version_id

        await apply_seed(session)
        await session.commit()

    async with sessionmaker() as session:
        prompt = await get_prompt_by_key(session, "extraction-meeting")
        assert prompt.current_published_version_id == published_version_id_before


async def test_reseeding_after_prompt_drift_publishes_a_new_version(app_env) -> None:  # noqa: ANN001
    """A published PromptVersion's content is DB-enforced immutable (see
    app.templates.models's before_update listener), so "drift" can only
    ever mean the SOURCE constants changed since the version was published
    — exactly what happens when a prompt wording fix like this one lands.
    Exercises `_republish_prompt_if_drifted` directly with a stand-in for
    "the old, already-published source wording" instead of illegally
    mutating a published row."""
    from app.templates.seed import _republish_prompt_if_drifted

    _, sessionmaker = app_env
    async with sessionmaker() as session:
        await apply_seed(session)
        await session.commit()

    async with sessionmaker() as session:
        prompt = await get_prompt_by_key(session, "extraction-meeting")
        assert prompt is not None
        old_version_id = prompt.current_published_version_id
        assert old_version_id is not None

    async with sessionmaker() as session:
        await _republish_prompt_if_drifted(
            session,
            prompt_key="extraction-meeting",
            system_prompt="a completely different system prompt",
            instructions={"agenda_topic": "x", "decision": "y", "action_item": "z"},
        )
        await session.commit()

    async with sessionmaker() as session:
        prompt = await get_prompt_by_key(session, "extraction-meeting")
        assert prompt is not None
        assert prompt.current_published_version_id != old_version_id

        new_version = await session.get(PromptVersion, prompt.current_published_version_id)
        assert new_version is not None
        assert new_version.status == VersionLifecycleStatus.PUBLISHED.value
        assert new_version.category_instructions["action_item"] == "z"

        retired_old_version = await session.get(PromptVersion, old_version_id)
        assert retired_old_version.status == VersionLifecycleStatus.RETIRED.value

        all_versions = (
            (
                await session.execute(
                    select(PromptVersion).where(PromptVersion.prompt_id == prompt.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(all_versions) == 2

    # Re-seeding again with the CURRENT real source constants (unchanged
    # from the very first apply_seed call) detects the drift once more and
    # republishes back to them -- never silently duplicates a version once
    # content actually does match again.
    async with sessionmaker() as session:
        await apply_seed(session)
        await session.commit()

    async with sessionmaker() as session:
        prompt = await get_prompt_by_key(session, "extraction-meeting")
        assert prompt is not None
        final_version = await session.get(PromptVersion, prompt.current_published_version_id)
        assert final_version is not None
        assert "speaker label" in final_version.category_instructions["action_item"]

        all_versions = (
            (
                await session.execute(
                    select(PromptVersion).where(PromptVersion.prompt_id == prompt.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(all_versions) == 3

        # Calling it yet again with the same, now-current content is a
        # true no-op.
        current_version_id = prompt.current_published_version_id
        await apply_seed(session)
        await session.commit()
        prompt = await get_prompt_by_key(session, "extraction-meeting")
        assert prompt.current_published_version_id == current_version_id


async def test_reseeding_never_touches_unpublished_foundation_templates(app_env) -> None:  # noqa: ANN001
    """medical_consultation/psychotherapy are seeded DRAFT-only (never
    published) -- their prompt has no current_published_version_id, so the
    drift check has nothing to compare against and must not raise."""
    _, sessionmaker = app_env
    async with sessionmaker() as session:
        await apply_seed(session)
        await session.commit()
        await apply_seed(session)
        await session.commit()

    async with sessionmaker() as session:
        prompt = await get_prompt_by_key(session, "extraction-medical_consultation")
        assert prompt is not None
        assert prompt.current_published_version_id is None
