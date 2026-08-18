# AI worker image (worker-speech / worker-diarization) — separate from
# backend/Dockerfile (the api/frontend-facing image) because this one
# installs the [ai] extra (faster-whisper, pyannote.audio, torch,
# torchaudio, ...) and a real FFmpeg binary, both multi-hundred-MB. The
# api/frontend images never get GPU device access or these packages (spec:
# "GPU isolation" — see deploy/docker-compose.yml).
#
# Base image: same pinned python:3.11-slim-trixie as backend/Dockerfile —
# see that file's comments for the trixie-over-bookworm CVE rationale,
# which applies identically here.
FROM python:3.11-slim-trixie@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends curl xz-utils ca-certificates \
    && apt-get remove -y --purge --allow-remove-essential perl-base \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# FFmpeg: an LGPL-configured static build (NOT Debian's own `ffmpeg`
# package, which is built with --enable-gpl — see
# docs/architecture/adr/0019-ffmpeg-normalization.md for the full audit).
# Source: https://github.com/BtbN/FFmpeg-Builds (BtbN/FFmpeg-Builds is
# itself MIT-licensed tooling; the *ffmpeg binary it produces* carries
# ffmpeg's own LGPL-3.0 license, confirmed via the build's own
# LICENSE.txt and `ffmpeg -version`'s configuration string showing no
# --enable-gpl/--enable-nonfree and libx264/libx265/libxavs2/libxvid all
# --disable'd). The `latest` release tag is a continuously-updated rolling
# build, so this Dockerfile pins by content hash (sha256) rather than by
# tag/commit — if upstream ever republishes different bytes under the same
# tag, this build fails closed (checksum mismatch) instead of silently
# accepting a different, unaudited binary.
ARG FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-lgpl.tar.xz
ARG FFMPEG_SHA256=079be6e766720bf2b1e1d71073214a51cae831295cbcc92e64d31e422fcb5ec1
RUN curl -sL -o /tmp/ffmpeg.tar.xz "$FFMPEG_URL" \
    && echo "${FFMPEG_SHA256}  /tmp/ffmpeg.tar.xz" | sha256sum -c - \
    && mkdir -p /tmp/ffmpeg-extract \
    && tar xf /tmp/ffmpeg.tar.xz -C /tmp/ffmpeg-extract --strip-components=1 \
    && install -m 0755 /tmp/ffmpeg-extract/bin/ffmpeg /usr/local/bin/ffmpeg \
    && install -m 0755 /tmp/ffmpeg-extract/bin/ffprobe /usr/local/bin/ffprobe \
    && install -Dm 0644 /tmp/ffmpeg-extract/LICENSE.txt /usr/share/doc/ffmpeg/LICENSE.txt \
    && rm -rf /tmp/ffmpeg.tar.xz /tmp/ffmpeg-extract \
    && apt-get purge -y xz-utils \
    && apt-get autoremove -y

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && rm -rf /usr/local/lib/python3.11/ensurepip/_bundled

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

# CPU-only torch/torchaudio wheels by default (smaller image, no CUDA
# runtime baked in) — an NVIDIA GPU still works at runtime via the host's
# NVIDIA Container Toolkit + a CUDA-enabled torch install; see
# docs/operations/gpu-runtime.md for the explicit swap-in instructions.
# This keeps the default worker image usable on CPU-only hosts too (spec:
# "CPU fallback where practical").
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu ".[ai]"

RUN useradd --create-home --uid 10001 vocadox
RUN mkdir -p /app/data/models /app/data/media /app/data/tmp-uploads \
    && chown -R vocadox:vocadox /app/data

USER vocadox

# Overridden per-service in deploy/docker-compose.yml (--role speech |
# diarization).
ENTRYPOINT ["python", "-m", "app.workers.runner"]
CMD ["--role", "speech"]
