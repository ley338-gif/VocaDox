"""Centralized conversation state-transition policy.

Every state change to `Conversation.status` must go through
`transition()` — no route or service function may assign
`conversation.status = "whatever"` directly. This is the single source of
truth for which transitions are valid, matching exactly the states that
genuinely exist in Phase 2 (see `app.conversations.models.ConversationStatus`
and its docstring on why TRANSCRIBING/DIARIZING/etc. are deliberately
absent).
"""

from __future__ import annotations

from app.conversations.models import ConversationStatus

# Explicit adjacency list of the only transitions Phase 2 allows.
_ALLOWED_TRANSITIONS: dict[ConversationStatus, set[ConversationStatus]] = {
    ConversationStatus.CREATED: {
        ConversationStatus.RECORDING,
        ConversationStatus.UPLOADED,
        ConversationStatus.DELETED,
        ConversationStatus.FAILED,
    },
    ConversationStatus.RECORDING: {
        ConversationStatus.UPLOADED,
        ConversationStatus.FAILED,
        ConversationStatus.DELETED,
    },
    ConversationStatus.UPLOADED: {
        ConversationStatus.NORMALIZING,
        ConversationStatus.READY,
        ConversationStatus.FAILED,
        ConversationStatus.DELETED,
    },
    ConversationStatus.NORMALIZING: {
        ConversationStatus.TRANSCRIBING,
        ConversationStatus.READY,
        ConversationStatus.FAILED,
        ConversationStatus.DELETED,
    },
    # Phase 3: real async processing stages. TRANSCRIBING and DIARIZING are
    # not required to be sequential (diarization runs against the same
    # normalized audio independently of transcription) — both may follow
    # NORMALIZING, and either may lead into ALIGNING once both underlying
    # ProcessingRuns exist (see app.processing.orchestrator).
    ConversationStatus.TRANSCRIBING: {
        ConversationStatus.DIARIZING,
        ConversationStatus.ALIGNING,
        ConversationStatus.READY,
        ConversationStatus.FAILED,
        ConversationStatus.DELETED,
    },
    ConversationStatus.DIARIZING: {
        ConversationStatus.ALIGNING,
        ConversationStatus.READY,
        ConversationStatus.FAILED,
        ConversationStatus.DELETED,
    },
    ConversationStatus.ALIGNING: {
        ConversationStatus.READY,
        ConversationStatus.FAILED,
        ConversationStatus.DELETED,
    },
    ConversationStatus.READY: {
        # A user-triggered reprocess ("reprocess with current profile", spec)
        # re-enters the pipeline from a READY conversation without losing
        # processing history (previous Transcript rows/ProcessingRuns are
        # never deleted — see app.processing.orchestrator.start_transcription).
        ConversationStatus.TRANSCRIBING,
        # Phase 4: an explicitly user-triggered EXTRACT job (never automatic —
        # see app.intelligence.router) moves a READY conversation into
        # EXTRACTING and back to READY on completion/failure. VALIDATING/
        # REVIEW_REQUIRED/READY_FOR_APPROVAL/APPROVED remain out of scope
        # (Phase 5's review/approval workflow) — see
        # docs/architecture/domain-model.md.
        ConversationStatus.EXTRACTING,
        ConversationStatus.DELETED,
    },
    ConversationStatus.EXTRACTING: {
        ConversationStatus.READY,
        ConversationStatus.FAILED,
        ConversationStatus.DELETED,
    },
    ConversationStatus.FAILED: {
        ConversationStatus.UPLOADED,  # retry a fresh upload after a failure
        ConversationStatus.NORMALIZING,
        ConversationStatus.TRANSCRIBING,
        ConversationStatus.EXTRACTING,
        ConversationStatus.DELETED,
    },
    ConversationStatus.DELETED: set(),
}


class InvalidTransitionError(ValueError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot transition conversation from {current!r} to {target!r}")
        self.current = current
        self.target = target


def is_valid_transition(current: ConversationStatus, target: ConversationStatus) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def transition(current: ConversationStatus, target: ConversationStatus) -> ConversationStatus:
    """Validate and return the new status, or raise InvalidTransitionError.
    Callers apply the returned value to `conversation.status` — this
    function never mutates anything itself, so it stays trivially unit
    testable without a DB."""
    if not is_valid_transition(current, target):
        raise InvalidTransitionError(current.value, target.value)
    return target
