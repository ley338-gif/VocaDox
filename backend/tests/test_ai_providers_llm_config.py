"""Phase 12 GA fix: VocaDox no longer bundles an `ollama` Compose service
(removed for GA — see docs/architecture/adr/0029-remove-bundled-ollama.md,
CVE-2026-56854), so `VOCADOX_LLM_BASE_URL` no longer has a default pointing
at a container that doesn't exist any more. `get_llm_provider`/
`get_llm_provider_for_model_identifier` must fail clearly and immediately
(LLMModelUnavailableError) when `llm_provider="ollama"` but no base URL is
configured — never silently hand back a provider that will just time out
against a made-up host."""

from __future__ import annotations

import pytest
from app.core.ai_providers import get_llm_provider, get_llm_provider_for_model_identifier
from app.platform.config import Settings
from app.providers.llm import FakeLLMProvider, LLMModelUnavailableError, OllamaLLMProvider


def test_llm_base_url_has_no_default() -> None:
    """The old default (`http://ollama:11434`) pointed at a container that
    no longer exists in `deploy/docker-compose.yml` — there must be no
    replacement default either, since there's no well-known bundled host
    any more."""
    assert Settings.model_fields["llm_base_url"].default is None


def test_get_llm_provider_defaults_to_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.ai_providers.get_settings", lambda: Settings(llm_provider="fake")
    )
    assert isinstance(get_llm_provider(), FakeLLMProvider)


def test_get_llm_provider_ollama_without_base_url_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.ai_providers.get_settings",
        lambda: Settings(llm_provider="ollama", llm_base_url=None),
    )
    with pytest.raises(LLMModelUnavailableError, match="VOCADOX_LLM_BASE_URL"):
        get_llm_provider()


def test_get_llm_provider_ollama_with_base_url_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.ai_providers.get_settings",
        lambda: Settings(llm_provider="ollama", llm_base_url="http://localhost:11434"),
    )
    assert isinstance(get_llm_provider(), OllamaLLMProvider)


def test_get_llm_provider_for_model_identifier_ollama_without_base_url_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.ai_providers.get_settings",
        lambda: Settings(llm_base_url=None),
    )
    with pytest.raises(LLMModelUnavailableError, match="VOCADOX_LLM_BASE_URL"):
        get_llm_provider_for_model_identifier(provider="ollama", model_identifier="qwen2.5:14b")
