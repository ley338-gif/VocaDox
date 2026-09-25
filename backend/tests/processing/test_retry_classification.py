"""An unreachable Ollama server is a transient, auto-retried failure — not
MODEL_UNAVAILABLE (which is never retried and tells the admin the model is
missing, sending them in the wrong direction)."""

from __future__ import annotations

import httpx
import pytest
from app.processing.models import FailureClass
from app.processing.retry import classify_exception, is_retryable
from app.providers.llm import (
    LLMModelUnavailableError,
    LLMServerUnreachableError,
    OllamaConfig,
    OllamaLLMProvider,
)


@pytest.mark.parametrize(
    "transport_error",
    [httpx.ConnectError("refused"), httpx.ConnectTimeout("syn timeout"), httpx.ReadTimeout("slow")],
)
async def test_ollama_transport_errors_are_transient(
    monkeypatch: pytest.MonkeyPatch, transport_error: httpx.HTTPError
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise transport_error

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    provider = OllamaLLMProvider(OllamaConfig(base_url="http://ollama.invalid:11434"))

    with pytest.raises(LLMServerUnreachableError) as exc_info:
        await provider.complete("prompt")

    failure_class = classify_exception(exc_info.value)
    assert failure_class is FailureClass.TRANSIENT
    assert is_retryable(failure_class)


async def test_missing_model_is_still_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(404)), **kwargs
        ),
    )
    provider = OllamaLLMProvider(OllamaConfig(base_url="http://ollama.invalid:11434"))

    with pytest.raises(LLMModelUnavailableError) as exc_info:
        await provider.complete("prompt")

    assert classify_exception(exc_info.value) is FailureClass.MODEL_UNAVAILABLE
