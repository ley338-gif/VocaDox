"""Centralized document-revision state-transition policy — the Phase 5
counterpart of app.conversations.state_machine. Every change to a
`Document`/`DocumentRevision`'s status must go through `transition()`; no
route or service function may assign `.status = "whatever"` directly.

Spec §27: `DRAFT -> REVIEW_REQUIRED -> READY_FOR_APPROVAL -> APPROVED`.
**The AI must never set APPROVED** — see app.documents.service, which is
the only caller of `transition(..., target=DocumentRevisionStatus.APPROVED)`
and only reaches it from a route requiring a human user holding
`document:approve`.
"""

from __future__ import annotations

from app.documents.models import DocumentRevisionStatus

_ALLOWED_TRANSITIONS: dict[DocumentRevisionStatus, set[DocumentRevisionStatus]] = {
    DocumentRevisionStatus.DRAFT: {
        DocumentRevisionStatus.REVIEW_REQUIRED,
        DocumentRevisionStatus.READY_FOR_APPROVAL,
    },
    DocumentRevisionStatus.REVIEW_REQUIRED: {
        DocumentRevisionStatus.READY_FOR_APPROVAL,
        # Re-composing while issues remain open produces another
        # REVIEW_REQUIRED revision rather than looping in place; this
        # entry exists so a same-status "transition" (idempotent no-op via
        # is_valid_transition's caller) is never treated as invalid.
        DocumentRevisionStatus.REVIEW_REQUIRED,
    },
    DocumentRevisionStatus.READY_FOR_APPROVAL: {
        DocumentRevisionStatus.APPROVED,
        # A fresh compose() after new facts/corrections can re-open review.
        DocumentRevisionStatus.REVIEW_REQUIRED,
        DocumentRevisionStatus.READY_FOR_APPROVAL,
    },
    # APPROVED has no outgoing transitions at all — an approved revision
    # never becomes anything else (see DocumentRevision's before_update
    # guard for the hard enforcement of this). Any further change produces
    # a brand new revision starting again at DRAFT/REVIEW_REQUIRED/
    # READY_FOR_APPROVAL.
    DocumentRevisionStatus.APPROVED: set(),
}


class InvalidDocumentTransitionError(ValueError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot transition document revision from {current!r} to {target!r}")
        self.current = current
        self.target = target


def is_valid_transition(
    current: DocumentRevisionStatus, target: DocumentRevisionStatus
) -> bool:
    if current == target:
        return True
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def transition(
    current: DocumentRevisionStatus, target: DocumentRevisionStatus
) -> DocumentRevisionStatus:
    if not is_valid_transition(current, target):
        raise InvalidDocumentTransitionError(current.value, target.value)
    return target
