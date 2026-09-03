"""LLM provider abstraction (used for intelligence extraction / summarization).

`OllamaLLMProvider` (real, local — see
docs/architecture/adr/0024-llm-provider-selection.md for the full
evaluation) is the Phase 4 production provider: a thin HTTP client against
a locally-run Ollama server (never a hosted/cloud API — spec explicitly
prioritizes local inference so conversation content never leaves the
deployment). `FakeLLMProvider` remains what CI/unit tests/GPU-less dev use
exclusively — never the real provider (see .github/workflows/ci.yml).

Structured output: `complete_structured` asks Ollama for JSON-Schema-
constrained output (Ollama's `format` request field accepts a JSON Schema
object directly since Ollama >=0.5) so extraction never depends on the
model "remembering" to emit valid JSON unprompted. Even so, callers MUST
still validate the returned text against their Pydantic schema themselves
(app.intelligence.schemas) — constrained decoding narrows the *shape* but
never guarantees semantic correctness, and a provider too old to support
`format` degrades to plain best-effort JSON, so this is not optional.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class LLMModelUnavailableError(RuntimeError):
    """Raised when the configured LLM/model is not installed/reachable.
    Callers (the worker) must catch this and classify the job failure as
    MODEL_UNAVAILABLE (app.processing.models.FailureClass) — never crash
    the worker process."""


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model_name: str


@dataclass(frozen=True, slots=True)
class LLMProviderStatus:
    provider: str
    model: str
    model_revision: str | None
    installed: bool
    device: str
    structured_output: bool
    detail: str | None = None


class LLMProvider(ABC):
    """Real implementations (Ollama, ...) land in Phase 4. Interface only here.

    Callers must never log the `prompt` argument or the returned `text`
    verbatim (spec §63) — only opaque metadata such as token counts/model
    name may be logged.
    """

    @abstractmethod
    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    async def complete_structured(
        self,
        prompt: str,
        *,
        json_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Request output constrained to `json_schema` where the provider
        supports it. Returns the raw JSON text — caller validates it
        against its own Pydantic model; a provider must never silently
        strip/repair invalid output on the caller's behalf."""
        raise NotImplementedError

    @abstractmethod
    def status(self) -> LLMProviderStatus:
        raise NotImplementedError


class FakeLLMProvider(LLMProvider):
    """Deterministic synthetic completion for tests and local dev. Never
    fabricates plausible-looking facts — `complete_structured` returns a
    minimal, schema-shaped, deliberately-empty/"not mentioned" payload so
    tests can exercise the uncertainty path without a real model."""

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        return LLMResponse(
            text=f"[fake completion for prompt of length {len(prompt)}]",
            model_name="fake-llm-v0",
        )

    async def complete_structured(
        self,
        prompt: str,
        *,
        json_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        import json

        empty = _empty_instance_for_schema(json_schema)
        return LLMResponse(text=json.dumps(empty), model_name="fake-llm-v0")

    def status(self) -> LLMProviderStatus:
        return LLMProviderStatus(
            provider="fake",
            model="fake-deterministic",
            model_revision=None,
            installed=True,
            device="cpu",
            structured_output=True,
            detail="Deterministic fake provider for tests/dev — never used in production.",
        )


def _empty_instance_for_schema(schema: dict[str, Any]) -> Any:
    """Best-effort minimal instance matching a JSON Schema's declared
    shape, used only by FakeLLMProvider so fake-provider tests exercise
    real Pydantic validation rather than a hand-authored fixture that
    could drift from the schema."""
    schema_type = schema.get("type")
    if schema_type == "object":
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        return {
            key: _empty_instance_for_schema(sub) for key, sub in props.items() if key in required
        }
    if schema_type == "array":
        return []
    if schema_type == "string":
        enum = schema.get("enum")
        return enum[0] if enum else ""
    if schema_type == "number":
        return 0.0
    if schema_type == "integer":
        return 0
    if schema_type == "boolean":
        return False
    return None


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    """Everything needed to describe the real provider without hardcoding
    a model identifier anywhere in worker code (spec: "don't hardcode
    model identifiers in worker code") — the actual identifier comes from
    a `ModelProfile` row (app.profiles.models), this is just the transport
    config."""

    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:14b"
    timeout_seconds: float = 300.0


class OllamaLLMProvider(LLMProvider):
    """Real local LLM inference via a locally-run Ollama server (MIT
    licensed runtime — see compliance/dependency-inventory.yml and
    docs/architecture/adr/0024-llm-provider-selection.md). Conversation
    content is sent only to `config.base_url`, never to any external/cloud
    endpoint."""

    def __init__(self, config: OllamaConfig) -> None:
        self._config = config

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - exercised only when dep is missing
            raise LLMModelUnavailableError("httpx is not installed in this environment") from exc

        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.post(
                    f"{self._config.base_url}/api/generate", json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError as exc:
            raise LLMModelUnavailableError(
                f"could not reach Ollama server at {self._config.base_url} — is it running? "
                "(see docs/admin/llm-provider.md)"
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise LLMModelUnavailableError(
                    f"model '{self._config.model}' is not installed on the Ollama server — run "
                    f"`ollama pull {self._config.model}` (see docs/admin/llm-provider.md)"
                ) from exc
            raise LLMModelUnavailableError(f"Ollama request failed: {exc}") from exc

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._config.model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt is not None:
            payload["system"] = system_prompt
        data = await self._post(payload)
        return LLMResponse(text=data.get("response", ""), model_name=self._config.model)

    async def complete_structured(
        self,
        prompt: str,
        *,
        json_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._config.model,
            "prompt": prompt,
            "stream": False,
            "format": json_schema,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        if system_prompt is not None:
            payload["system"] = system_prompt
        data = await self._post(payload)
        return LLMResponse(text=data.get("response", ""), model_name=self._config.model)

    def status(self) -> LLMProviderStatus:
        """Uses a sync HTTP call (deliberately, matching the other
        providers' sync `status()` signature) — a short, rare, timeout-
        bounded check, never called from a hot path."""
        installed = False
        detail: str | None = None
        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self._config.base_url}/api/tags")
                response.raise_for_status()
                tags = response.json().get("models", [])
                names = {m.get("name") for m in tags}
                if self._config.model in names or any(
                    (n or "").startswith(self._config.model.split(":")[0]) for n in names
                ):
                    installed = True
                else:
                    detail = f"model '{self._config.model}' not found on Ollama server"
        except Exception as exc:  # noqa: BLE001 - status check must never raise
            detail = f"Ollama server unreachable: {type(exc).__name__}"

        return LLMProviderStatus(
            provider="ollama",
            model=self._config.model,
            model_revision=None,
            installed=installed,
            device="auto",
            structured_output=True,
            detail=detail,
        )
