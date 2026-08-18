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


def test_created_to_transcribing_does_not_exist() -> None:
    # TRANSCRIBING isn't even a member of ConversationStatus in Phase 2 —
    # this asserts the enum itself, guarding against it being added back
    # accidentally before Phase 3 is approved.
    assert not hasattr(ConversationStatus, "TRANSCRIBING")
    assert not hasattr(ConversationStatus, "DIARIZING")
    assert not hasattr(ConversationStatus, "APPROVED")


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
