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


def detect_device_capabilities() -> DeviceCapabilities:
    """Best-effort, exception-safe. Any detection failure (torch missing,
    driver issue) degrades to "no CUDA, CPU-only" rather than crashing —
    provider status endpoints must always be able to render something
    understandable."""
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
    return DeviceCapabilities(
        cuda_available=False, device_name=None, total_vram_mb=None, free_vram_mb=None
    )


def select_device(*, prefer_gpu: bool = True) -> str:
    caps = detect_device_capabilities()
    if prefer_gpu and caps.cuda_available:
        return "cuda"
    return "cpu"
