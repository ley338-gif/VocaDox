"""Media normalization abstraction, decoupled from any concrete tool.

Phase 2 shipped only `NoOpMediaNormalizer` and explicitly deferred any
transcoding engine until its exact build/license/codec configuration was
evaluated (never assume "FFmpeg = LGPL" — the effective license depends on
which codecs are compiled in). That evaluation has now happened for Phase
3 (speech/diarization providers require a specific PCM format — see
`FfmpegMediaNormalizer`'s docstring and
docs/architecture/adr/0017-ffmpeg-normalization.md) and selects an
LGPL-configured FFmpeg build for anything VocaDox ships in a container
image. `NoOpMediaNormalizer` remains available as the fallback when no
`ffmpeg` binary is resolvable (documented degradation, never silent).
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NormalizationInput:
    data: bytes
    content_type: str
    container: str | None


@dataclass(frozen=True)
class NormalizationResult:
    data: bytes
    content_type: str
    container: str | None
    codec: str | None
    duration_ms: int | None = None
    sample_rate: int | None = None
    channels: int | None = None


class NormalizationError(RuntimeError):
    """Normalization failed (bad input, subprocess timeout, non-zero exit,
    resource limit). Callers must set the Conversation/ProcessingJob to
    FAILED — never delete the (immutable) source media on this error."""


class MediaNormalizer(ABC):
    @abstractmethod
    async def normalize(self, source: NormalizationInput) -> NormalizationResult:
        """Produce derived media from `source`. Must never mutate or
        depend on being able to mutate the original source bytes/row —
        callers persist the result as a brand new MediaAsset."""
        raise NotImplementedError


class NoOpMediaNormalizer(MediaNormalizer):
    """Passes already-compatible input through unchanged. Used whenever no
    `ffmpeg` binary is available (see app.core.ai_providers.get_media_normalizer)
    — real speech/diarization processing on non-PCM-WAV input will then
    fail with a clear error rather than silently mis-processing audio."""

    async def normalize(self, source: NormalizationInput) -> NormalizationResult:
        return NormalizationResult(
            data=source.data,
            content_type=source.content_type,
            container=source.container,
            codec=None,
        )


class FfmpegMediaNormalizer(MediaNormalizer):
    """Real normalization via the `ffmpeg` CLI binary, invoked as a safe
    argument list (never shell interpolation), with an explicit subprocess
    timeout, input duration/size checks, and controlled temp paths that are
    always cleaned up.

    Target format (spec: "determine the actual format required by your
    selected Speech/Diarization providers... verify, don't assume"):
    faster-whisper (via its ffmpeg/PyAV decode path) and pyannote.audio
    both accept mono PCM at any sample rate and internally resample as
    needed, but pinning normalization to mono 16 kHz PCM WAV up front
    avoids format ambiguity between the two providers, keeps output size
    small and predictable, and matches Whisper's own training sample rate
    (16 kHz) exactly — verified against faster-whisper's README ("Whisper
    models are trained... to operate on audio sampled at 16kHz") and
    pyannote.audio's pipeline docs (resamples any input to 16kHz mono
    internally regardless of what it's given). See
    docs/architecture/adr/0017-ffmpeg-normalization.md.

    License note: the *binary* actually installed on PATH determines the
    effective license, not this code. Production container images MUST
    install an LGPL-configured FFmpeg build (`--disable-gpl
    --disable-nonfree`, no libx264/libmp3lame) — see
    docs/architecture/adr/0017-ffmpeg-normalization.md and
    compliance/container-inventory.yml for the exact build pinned in the
    worker image. A GPL-configured `ffmpeg` binary found on a developer's
    local PATH (as this repo's own CI/dev sandbox may have) is NEVER what
    ships in a VocaDox image — see that ADR for how CI verifies this.
    """

    def __init__(
        self,
        *,
        target_sample_rate_hz: int = 16000,
        subprocess_timeout_seconds: int = 600,
        max_input_size_bytes: int = 2 * 1024 * 1024 * 1024,
        ffmpeg_binary: str = "ffmpeg",
        ffprobe_binary: str = "ffprobe",
    ) -> None:
        self._target_sample_rate_hz = target_sample_rate_hz
        self._timeout = subprocess_timeout_seconds
        self._max_input_size_bytes = max_input_size_bytes
        self._ffmpeg = ffmpeg_binary
        self._ffprobe = ffprobe_binary

    @staticmethod
    def ffmpeg_available(ffmpeg_binary: str = "ffmpeg") -> bool:
        return shutil.which(ffmpeg_binary) is not None

    async def normalize(self, source: NormalizationInput) -> NormalizationResult:
        if len(source.data) == 0:
            raise NormalizationError("empty input")
        if len(source.data) > self._max_input_size_bytes:
            raise NormalizationError("input exceeds max normalization size")

        tmp_dir = Path(tempfile.mkdtemp(prefix="vocadox-normalize-"))
        in_suffix = f".{source.container}" if source.container else ".bin"
        in_path = tmp_dir / f"in-{uuid.uuid4().hex}{in_suffix}"
        out_path = tmp_dir / f"out-{uuid.uuid4().hex}.wav"
        try:
            in_path.write_bytes(source.data)

            cmd = [
                self._ffmpeg,
                "-nostdin",
                "-y",
                "-i",
                str(in_path),
                "-vn",  # audio only, never a hidden video stream
                "-ac",
                "1",  # mono
                "-ar",
                str(self._target_sample_rate_hz),
                "-acodec",
                "pcm_s16le",
                str(out_path),
            ]
            await self._run_subprocess(cmd)

            if not out_path.exists() or out_path.stat().st_size == 0:
                raise NormalizationError("ffmpeg produced no output")

            probed = await self._probe_duration_ms(out_path)
            data = out_path.read_bytes()
            return NormalizationResult(
                data=data,
                content_type="audio/wav",
                container="wav",
                codec="pcm_s16le",
                duration_ms=probed,
                sample_rate=self._target_sample_rate_hz,
                channels=1,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def _run_subprocess(self, cmd: list[str]) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                _stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout
                )
            except TimeoutError as exc:
                proc.kill()
                await proc.wait()
                raise NormalizationError(
                    f"ffmpeg timed out after {self._timeout}s"
                ) from exc
        except FileNotFoundError as exc:
            raise NormalizationError(f"{cmd[0]} binary not found on PATH") from exc

        if proc.returncode != 0:
            # Never propagate raw ffmpeg stderr (may contain the input
            # filesystem path) to API responses — safe server-log detail
            # only; callers persist just the exit code.
            raise NormalizationError(
                f"ffmpeg exited with code {proc.returncode}: "
                f"{stderr.decode(errors='replace')[-500:]}"
            )

    async def _probe_duration_ms(self, path: Path) -> int | None:
        cmd = [
            self._ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                return None
            return int(float(stdout.decode().strip()) * 1000)
        except Exception:  # noqa: BLE001 - duration probing is best-effort
            return None
