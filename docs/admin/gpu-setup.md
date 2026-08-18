# GPU setup

## Is a GPU required?

No. Both providers support CPU inference (`compute_type=int8` for
faster-whisper; pyannote runs on CPU by default). A GPU makes processing
substantially faster, especially for longer recordings, but VocaDox is
usable CPU-only.

## Enabling GPU access

1. Install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
   on the Docker host.
2. In `deploy/docker-compose.yml`, uncomment the `deploy.resources.reservations.devices`
   block under `worker-speech` and/or `worker-diarization`:
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]
   ```
3. Set `VOCADOX_SPEECH_DEVICE=cuda` / `VOCADOX_DIARIZATION_DEVICE=cuda`
   (or leave `auto` — both providers auto-detect CUDA availability via
   `app/providers/device.py` and fall back to CPU if none is found).
4. `backend/worker.Dockerfile` installs **CPU-only** torch wheels by
   default (smaller image, no CUDA runtime baked in). For real GPU
   inference, rebuild with CUDA-enabled torch — swap the
   `--extra-index-url` in the Dockerfile's `pip install ... ".[ai]"` step
   to the matching CUDA wheel index (e.g.
   `https://download.pytorch.org/whl/cu121`) for your driver/CUDA
   version, or install it separately after the base image build.

## Verifying GPU is actually used

`GET /api/v1/admin/providers/speech` (and `.../diarization`) reports
`cuda_available` and `device` — `cuda_available: true` with
`device: "cuda"` confirms the worker sees and is using the GPU.
`nvidia-smi` on the host (or inside the worker container, if the toolkit
is installed) shows the process using VRAM during an active job.

## What was actually verified in this phase

This phase's real-model validation ran on a single NVIDIA GPU available
in the development sandbox — see PHASE_3_VALIDATION_REPORT.md's
Performance section for exact hardware, VRAM usage, and timing. Multi-GPU
allocation (pinning `worker-speech` to one GPU and `worker-diarization`
to another) is architecturally supported (each service gets its own
`deploy.resources` block) but was **not** exercised in this phase's
validation — mark that specific claim as NOT VERIFIED if you rely on it,
and test in your own environment before depending on it.
