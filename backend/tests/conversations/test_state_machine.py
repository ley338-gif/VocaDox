from __future__ import annotations

import pytest
from app.conversations.models import ConversationStatus
from app.conversations.state_machine import InvalidTransitionError, is_valid_transition, transition


def test_created_to_recording_is_valid() -> None:
    assert (
        transition(ConversationStatus.CREATED, ConversationStatus.RECORDING)
        == ConversationStatus.RECORDING
    )


def test_created_to_uploaded_is_valid_for_file_upload_path() -> None:
    assert (
        transition(ConversationStatus.CREATED, ConversationStatus.UPLOADED)
        == ConversationStatus.UPLOADED
    )


def test_uploaded_to_ready_is_valid() -> None:
    assert (
        transition(ConversationStatus.UPLOADED, ConversationStatus.READY)
        == ConversationStatus.READY
    )


def test_uploaded_to_normalizing_to_ready_is_valid() -> None:
    assert is_valid_transition(ConversationStatus.UPLOADED, ConversationStatus.NORMALIZING)
    assert is_valid_transition(ConversationStatus.NORMALIZING, ConversationStatus.READY)


def test_ready_to_recording_is_invalid() -> None:
    with pytest.raises(InvalidTransitionError):
        transition(ConversationStatus.READY, ConversationStatus.RECORDING)


def test_deleted_is_terminal() -> None:
    assert not is_valid_transition(ConversationStatus.DELETED, ConversationStatus.READY)
    assert not is_valid_transition(ConversationStatus.DELETED, ConversationStatus.RECORDING)


def test_phase4_extracting_now_exists_but_phase5_states_still_do_not() -> None:
    # TRANSCRIBING/DIARIZING/ALIGNING became real in Phase 3; EXTRACTING
    # became real in Phase 4 (see app.intelligence) — this now asserts the
    # *opposite* of the old Phase 3 guard for EXTRACTING, while continuing
    # to guard against Phase 5+ states (COMPOSING/APPROVED and friends)
    # being added before their own phase is approved.
    assert hasattr(ConversationStatus, "TRANSCRIBING")
    assert hasattr(ConversationStatus, "DIARIZING")
    assert hasattr(ConversationStatus, "ALIGNING")
    assert hasattr(ConversationStatus, "EXTRACTING")
    assert not hasattr(ConversationStatus, "COMPOSING")
    assert not hasattr(ConversationStatus, "APPROVED")
    assert not hasattr(ConversationStatus, "VALIDATING")
    assert not hasattr(ConversationStatus, "REVIEW_REQUIRED")
    assert not hasattr(ConversationStatus, "READY_FOR_APPROVAL")


def test_ready_to_extracting_is_valid_and_back() -> None:
    assert (
        transition(ConversationStatus.READY, ConversationStatus.EXTRACTING)
        == ConversationStatus.EXTRACTING
    )
    assert (
        transition(ConversationStatus.EXTRACTING, ConversationStatus.READY)
        == ConversationStatus.READY
    )


def test_failed_can_retry_to_uploaded() -> None:
    assert (
        transition(ConversationStatus.FAILED, ConversationStatus.UPLOADED)
        == ConversationStatus.UPLOADED
    )


def test_failed_to_recording_is_invalid() -> None:
    with pytest.raises(InvalidTransitionError):
        transition(ConversationStatus.FAILED, ConversationStatus.RECORDING)


def test_any_pre_delete_state_can_reach_deleted() -> None:
    for state in ConversationStatus:
        if state == ConversationStatus.DELETED:
            continue
        assert is_valid_transition(state, ConversationStatus.DELETED), state
