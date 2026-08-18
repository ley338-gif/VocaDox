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
        ConversationStatus.READY,
        ConversationStatus.FAILED,
        ConversationStatus.DELETED,
    },
    ConversationStatus.READY: {
        ConversationStatus.DELETED,
    },
    ConversationStatus.FAILED: {
        ConversationStatus.UPLOADED,  # retry a fresh upload after a failure
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
