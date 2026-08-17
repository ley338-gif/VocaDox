"""LLM provider abstraction (used for intelligence extraction / summarization)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model_name: str


class LLMProvider(ABC):
    """Real implementations (Ollama, ...) land in Phase 4. Interface only here.

    Callers must never log the `prompt` argument or the returned `text`
    verbatim (spec §63) — only opaque metadata such as token counts/model
    name may be logged.
    """

    @abstractmethod
    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        raise NotImplementedError


class FakeLLMProvider(LLMProvider):
    """Deterministic synthetic completion for tests and local dev."""

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        return LLMResponse(
            text=f"[fake completion for prompt of length {len(prompt)}]",
            model_name="fake-llm-v0",
        )
