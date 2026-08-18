"""Fake provider tests: verify deterministic synthetic output + storage semantics."""

from __future__ import annotations

import pytest
from app.providers import (
    FakeDiarizationProvider,
    FakeLLMProvider,
    FakeSpeechProvider,
    LocalFilesystemStorage,
)


async def test_fake_speech_provider_is_deterministic() -> None:
    provider = FakeSpeechProvider()
    result_a = await provider.transcribe("irrelevant.wav")
    result_b = await provider.transcribe("irrelevant.wav")
    assert result_a == result_b
    assert len(result_a.segments) > 0


async def test_fake_diarization_provider_is_deterministic() -> None:
    provider = FakeDiarizationProvider()
    result = await provider.diarize("irrelevant.wav")
    assert result.speaker_count == 2


async def test_fake_llm_provider_does_not_echo_prompt_verbatim() -> None:
    provider = FakeLLMProvider()
    response = await provider.complete("secret prompt content")
    assert "secret prompt content" not in response.text


async def test_local_filesystem_storage_roundtrip(tmp_path) -> None:
    storage = LocalFilesystemStorage(tmp_path)
    key = await storage.save(b"hello world", suffix=".txt")
    assert await storage.exists(key)
    assert await storage.load(key) == b"hello world"
    await storage.delete(key)
    assert not await storage.exists(key)


async def test_local_filesystem_storage_rejects_path_traversal(tmp_path) -> None:
    storage = LocalFilesystemStorage(tmp_path)
    with pytest.raises(ValueError):
        await storage.load("../../etc/passwd")
    with pytest.raises(ValueError):
        await storage.load("nested/../../escape.txt")
    with pytest.raises(ValueError):
        await storage.load("/etc/passwd")
    with pytest.raises(ValueError):
        await storage.load("..%2f..%2fetc%2fpasswd")


async def test_local_filesystem_storage_namespace_roundtrip(tmp_path) -> None:
    storage = LocalFilesystemStorage(tmp_path)
    key = await storage.save(
        b"hello", suffix=".wav", namespace="organizations/org1/conversations/conv1/source"
    )
    assert "/" in key
    assert await storage.exists(key)
    assert await storage.load(key) == b"hello"


async def test_local_filesystem_storage_namespace_rejects_dangerous_segments(tmp_path) -> None:
    storage = LocalFilesystemStorage(tmp_path)
    # A namespace segment that sanitizes down to nothing (e.g. "..", which
    # contains no alphanumeric/-/_ characters) is rejected outright rather
    # than silently continuing with an empty/ambiguous path segment.
    with pytest.raises(ValueError):
        await storage.save(b"hello", namespace="../../etc")


async def test_local_filesystem_storage_namespace_strips_unsafe_characters(tmp_path) -> None:
    storage = LocalFilesystemStorage(tmp_path)
    key = await storage.save(b"hello", namespace="org.1/conv#1")
    assert "." not in key.split("/")[0]
    assert "#" not in key
    assert await storage.load(key) == b"hello"
