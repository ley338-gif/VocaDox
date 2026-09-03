"""Retry policy: which FailureClass values are retried, and how many
times. Explicit, not "endless retry hidden behind exponential backoff
forever" — see ProcessingJob.max_attempts.
"""

from __future__ import annotations

from app.processing.models import FailureClass

# True = eligible for another attempt (subject to attempt < max_attempts).
RETRYABLE: dict[FailureClass, bool] = {
    FailureClass.TRANSIENT: True,
    FailureClass.RESOURCE: True,  # e.g. transient VRAM pressure; still capped by max_attempts
    FailureClass.PERMANENT: False,  # e.g. corrupt/unsupported audio
    FailureClass.INPUT_INVALID: False,
    FailureClass.MODEL_UNAVAILABLE: False,  # requires an admin action, not a blind retry
}


def is_retryable(failure_class: FailureClass) -> bool:
    return RETRYABLE.get(failure_class, False)


def classify_exception(exc: Exception) -> FailureClass:
    """Map a caught exception to a FailureClass. Conservative default
    (PERMANENT) when the cause is unrecognized, so an unknown error never
    silently retries forever."""
    from app.intelligence.service import ExtractionValidationError
    from app.media.normalizer import NormalizationError
    from app.media.validation import UploadValidationError
    from app.providers.diarization import DiarizationModelUnavailableError
    from app.providers.llm import LLMModelUnavailableError
    from app.providers.speech_to_text import SpeechModelUnavailableError

    if isinstance(
        exc,
        SpeechModelUnavailableError | DiarizationModelUnavailableError | LLMModelUnavailableError,
    ):
        return FailureClass.MODEL_UNAVAILABLE
    if isinstance(exc, UploadValidationError):
        return FailureClass.INPUT_INVALID
    if isinstance(exc, NormalizationError | ExtractionValidationError):
        return FailureClass.PERMANENT
    if isinstance(exc, MemoryError):
        return FailureClass.RESOURCE
    if isinstance(exc, TimeoutError | ConnectionError | OSError):
        return FailureClass.TRANSIENT
    return FailureClass.PERMANENT
