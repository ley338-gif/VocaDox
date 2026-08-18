# GPU runtime (operations)

See `docs/admin/gpu-setup.md` for the setup steps; this document covers
day-2 operational concerns.

## Requirements

- An NVIDIA GPU with a driver compatible with the CUDA version your
  installed `torch`/`torchaudio`/`ctranslate2` wheels expect.
- The [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  installed on the Docker host so `docker run --gpus`/Compose's
  `deploy.resources.reservations.devices: [nvidia]` actually passes the
  device through.

## Monitoring VRAM usage

`app/providers/device.py`'s `detect_device_capabilities()` reports
`total_vram_mb`/`free_vram_mb` via `torch.cuda.mem_get_info` — surfaced
indirectly through the admin provider-status endpoints (device/
cuda_available only; VRAM numbers aren't in the current API response, but
are available for future admin dashboards). For live monitoring, `nvidia-smi`
on the host remains the most direct tool.

## Multiple GPUs

Each worker service (`worker-speech`, `worker-diarization`) gets its own
independent `deploy.resources.reservations.devices` block — pin them to
different physical GPUs via Compose's device selection if you have more
than one. This was not exercised in this phase's sandbox validation
(single-GPU environment) — treat multi-GPU pinning as architecturally
supported but NOT VERIFIED until tested in your own environment.

## Fallback behavior

If `VOCADOX_SPEECH_DEVICE=auto` (or the diarization equivalent) and no
GPU is detected (or the GPU is busy/unavailable), the provider silently
runs on CPU — this is intentional graceful degradation, not a failure.
Check the admin provider-status endpoint's `device`/`cuda_available`
fields if throughput seems unexpectedly slow; it will honestly report
`device: "cpu"` if that's what's actually happening.

## Known limitations from this phase's validation

- Only CPU-only torch wheels were exercised in the AI worker image build
  verified by this phase's CI-equivalent testing (the mandatory CI itself
  never touches a GPU at all, by design). Real-model validation against
  an actual GPU was performed manually in the development sandbox — see
  PHASE_3_VALIDATION_REPORT.md's Performance section for the exact
  hardware/driver/CUDA versions used and results.
