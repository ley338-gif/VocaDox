"""Unit tests for app.providers.device's hardware-capability detection.

Includes a regression test for a real bug found during this phase's
GPU validation: a machine with faster-whisper installed but NOT torch
(a legitimate configuration — faster-whisper's ctranslate2 backend
doesn't require torch at all) silently reported cuda_available=False
even with a working GPU, purely because detection only ever tried
torch. Fixed by also trying ctranslate2's own CUDA device count when
torch is unavailable/reports no CUDA.
"""

from __future__ import annotations

from unittest.mock import patch

from app.providers.device import (
    DeviceCapabilities,
    detect_device_capabilities,
    select_device,
)


def test_detection_never_raises_when_no_backend_is_installed() -> None:
    # Simulate an environment where both torch and ctranslate2 imports fail.
    with patch("app.providers.device._detect_via_torch", return_value=None):
        with patch("app.providers.device._detect_via_ctranslate2", return_value=None):
            caps = detect_device_capabilities()
    assert caps.cuda_available is False
    assert caps.device_name is None


def test_ctranslate2_fallback_is_used_when_torch_reports_nothing() -> None:
    # Regression test: torch missing/no-CUDA must not mask a real GPU that
    # ctranslate2 (faster-whisper's runtime) can see independently.
    fallback = DeviceCapabilities(
        cuda_available=True, device_name=None, total_vram_mb=None, free_vram_mb=None
    )
    with patch("app.providers.device._detect_via_torch", return_value=None):
        with patch("app.providers.device._detect_via_ctranslate2", return_value=fallback):
            caps = detect_device_capabilities()
    assert caps.cuda_available is True


def test_torch_result_is_preferred_over_ctranslate2_when_both_available() -> None:
    torch_result = DeviceCapabilities(
        cuda_available=True, device_name="Fake GPU", total_vram_mb=8000, free_vram_mb=4000
    )
    with patch("app.providers.device._detect_via_torch", return_value=torch_result):
        caps = detect_device_capabilities()
    assert caps.device_name == "Fake GPU"


def test_select_device_prefers_gpu_when_available_and_requested() -> None:
    with patch(
        "app.providers.device.detect_device_capabilities",
        return_value=DeviceCapabilities(True, "GPU", 8000, 4000),
    ):
        assert select_device(prefer_gpu=True) == "cuda"
        assert select_device(prefer_gpu=False) == "cpu"


def test_select_device_falls_back_to_cpu_when_no_gpu() -> None:
    with patch(
        "app.providers.device.detect_device_capabilities",
        return_value=DeviceCapabilities(False, None, None, None),
    ):
        assert select_device(prefer_gpu=True) == "cpu"
