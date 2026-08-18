"""Provider abstractions (spec §69).

Interfaces for external/pluggable engines (speech-to-text, diarization, LLM)
plus one real implementation for local filesystem storage. Real engine
integrations (Whisper, pyannote, Ollama, ...) are Phase 3/4 work — Phase 0
only ships interfaces and deterministic Fake* implementations for tests.
"""

from app.providers.diarization import (
    DiarizationProvider,
    FakeDiarizationProvider,
    PyannoteDiarizationProvider,
)
from app.providers.llm import FakeLLMProvider, LLMProvider
from app.providers.speech_to_text import (
    FakeSpeechProvider,
    FasterWhisperSpeechProvider,
    SpeechToTextProvider,
)
from app.providers.storage import LocalFilesystemStorage, StorageProvider

__all__ = [
    "SpeechToTextProvider",
    "FakeSpeechProvider",
    "FasterWhisperSpeechProvider",
    "DiarizationProvider",
    "FakeDiarizationProvider",
    "PyannoteDiarizationProvider",
    "LLMProvider",
    "FakeLLMProvider",
    "StorageProvider",
    "LocalFilesystemStorage",
]
