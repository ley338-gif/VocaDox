"""Narrow hardware-capability detection for AI providers (Phase 3).

Scope is deliberately small per the spec ("narrow scope — CUDA available?
CPU mode? model can load? free VRAM if reliably available?") — this is
not a hardware inventory platform, and it never reports hardware serial
numbers or any other machine-identifying telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    cuda_available: bool
    device_name: str | None
    total_vram_mb: int | None
    free_vram_mb: int | None
    cpu_fallback_available: bool = True


def _detect_via_torch() -> DeviceCapabilities | None:
    """torch (pyannote.audio's runtime) reports the richest info (device
    name, free/total VRAM) when it's installed."""
    try:
        import torch

        if torch.cuda.is_available():
            index = torch.cuda.current_device()
            name = torch.cuda.get_device_name(index)
            free_bytes, total_bytes = torch.cuda.mem_get_info(index)
            return DeviceCapabilities(
                cuda_available=True,
                device_name=name,
                total_vram_mb=int(total_bytes / (1024 * 1024)),
                free_vram_mb=int(free_bytes / (1024 * 1024)),
            )
    except Exception:  # noqa: BLE001 - detection must never raise
        pass
    return None


def _detect_via_ctranslate2() -> DeviceCapabilities | None:
    """faster-whisper's runtime (ctranslate2) does NOT depend on torch —
    found via real testing (app.providers.speech_to_text.FasterWhisperSpeechProvider
    reported cuda_available=False on a machine with a working GPU, purely
    because torch happened not to be installed in that environment).
    ctranslate2 exposes its own CUDA device count, so a speech-only worker
    that never installs torch still gets honest GPU detection — no VRAM
    figures available via this path, only presence."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return DeviceCapabilities(
                cuda_available=True,
                device_name=None,
                total_vram_mb=None,
                free_vram_mb=None,
            )
    except Exception:  # noqa: BLE001 - detection must never raise
        pass
    return None


def detect_device_capabilities() -> DeviceCapabilities:
    """Best-effort, exception-safe. Any detection failure (neither torch
    nor ctranslate2 installed/working, driver issue) degrades to "no
    CUDA, CPU-only" rather than crashing — provider status endpoints must
    always be able to render something understandable."""
    return (
        _detect_via_torch()
        or _detect_via_ctranslate2()
        or DeviceCapabilities(
            cuda_available=False, device_name=None, total_vram_mb=None, free_vram_mb=None
        )
    )


def select_device(*, prefer_gpu: bool = True) -> str:
    caps = detect_device_capabilities()
    if prefer_gpu and caps.cuda_available:
        return "cuda"
    return "cpu"
