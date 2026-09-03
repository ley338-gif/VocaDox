# AI worker image (worker-speech / worker-diarization / worker-extraction)
# — separate from backend/Dockerfile (the api/frontend-facing image)
# because this one installs the [ai] extra (faster-whisper,
# pyannote.audio, torch, torchaudio, httpx, ...) and a real FFmpeg binary,
# both multi-hundred-MB. The api/frontend images never get GPU device
# access or these packages (spec: "GPU isolation" — see
# deploy/docker-compose.yml). Phase 4's worker-extraction role reuses this
# same image (it only needs httpx to call the separate `ollama` container
# over HTTP — no local model weights or GPU access of its own) rather than
# introducing a fourth, near-identical image.
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
# Phase 3.1: this pin was bumped after `docker compose build` genuinely
# failed closed exactly as designed — BtbN's `latest` tag had republished
# different bytes under the same tag since Phase 3 (a real occurrence of
# the rolling-tag risk this Dockerfile's original comment warned about,
# not a hypothetical). Re-verified before bumping: re-downloaded, hashed,
# and re-inspected `ffmpeg -version`'s configuration string for the same
# LGPL-only markers (`--enable-version3`, no `--enable-gpl`/
# `--enable-nonfree`, `libx264`/`libx265`/`libxavs2`/`libxvid` all still
# `--disable`d) before trusting the new hash — never bumped blindly just
# to unblock a build.
#
# Phase 4 CI hit this exact rolling-tag risk a second time (BtbN
# republished new bytes yet again, dated 2026-09-02, breaking the Docker
# build job with an unrelated-looking sha256 mismatch on an otherwise
# green PR) — re-verified the same way before bumping again: downloaded
# both archives fresh, confirmed `ffmpeg -version`'s configuration string
# still shows `--enable-version3`, no `--enable-gpl`/`--enable-nonfree`,
# `libx264`/`libx265`/`libxavs2`/`libxvid` still `--disable`d, and
# LICENSE.txt is still LGPL-3.0 text, before trusting the new hash.
ARG FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-lgpl.tar.xz
ARG FFMPEG_SHA256=5523b96d2aaa918597dc0e43c5e2e18a6a576fb4ee7c506c117ce3447351d6d2
RUN curl -sL -o /tmp/ffmpeg.tar.xz "$FFMPEG_URL" \
    && echo "${FFMPEG_SHA256}  /tmp/ffmpeg.tar.xz" | sha256sum -c - \
    && mkdir -p /tmp/ffmpeg-extract \
    && tar xf /tmp/ffmpeg.tar.xz -C /tmp/ffmpeg-extract --strip-components=1 \
    && install -m 0755 /tmp/ffmpeg-extract/bin/ffmpeg /usr/local/bin/ffmpeg \
    && install -m 0755 /tmp/ffmpeg-extract/bin/ffprobe /usr/local/bin/ffprobe \
    && install -Dm 0644 /tmp/ffmpeg-extract/LICENSE.txt /usr/share/doc/ffmpeg/LICENSE.txt \
    && rm -rf /tmp/ffmpeg.tar.xz /tmp/ffmpeg-extract

# torchcodec (a transitive dependency of pyannote.audio 4.x — see
# ADR-0017's account of the 3.x->4.x pin change, which moved pyannote off
# torchaudio's removed AudioMetaData API and onto torchcodec instead) does
# its own audio decoding via FFmpeg's *shared libraries*
# (libavutil.so/libavcodec.so/...), loaded with `ctypes`/`torch.ops.
# load_library` at first real use — a completely separate requirement
# from the `ffmpeg`/`ffprobe` CLI binaries installed above (which only
# VocaDox's own `FfmpegMediaNormalizer` subprocess-invokes). Found by real
# diarization inference testing, not by reading pyannote/torchcodec's
# docs: with only the CLI binaries present, actually calling the loaded
# pipeline against real audio failed with `OSError: Could not load this
# library: .../libtorchcodec_core*.so` / `libavutil.so.58: cannot open
# shared object file` — torchcodec was never able to find ANY FFmpeg
# shared library on the system, because none had ever been installed.
# Same BtbN source, same LGPL-only stance as above (never Debian's own
# GPL-configured `ffmpeg`/libav* packages) — just the "shared" build
# variant instead of "static", pinned by sha256 the same way. Re-bumped
# alongside the static archive above (Phase 4 CI, same BtbN republish) —
# LICENSE.txt re-verified as LGPL-3.0 text before trusting the new hash.
ARG FFMPEG_SHARED_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-lgpl-shared.tar.xz
ARG FFMPEG_SHARED_SHA256=03ce220a9c1458153771da538abbb699ba36a7eed911ea9067a01d66eb0b336d
RUN curl -sL -o /tmp/ffmpeg-shared.tar.xz "$FFMPEG_SHARED_URL" \
    && echo "${FFMPEG_SHARED_SHA256}  /tmp/ffmpeg-shared.tar.xz" | sha256sum -c - \
    && mkdir -p /tmp/ffmpeg-shared-extract \
    && tar xf /tmp/ffmpeg-shared.tar.xz -C /tmp/ffmpeg-shared-extract --strip-components=1 \
    && cp -P /tmp/ffmpeg-shared-extract/lib/*.so* /usr/local/lib/ \
    && install -Dm 0644 /tmp/ffmpeg-shared-extract/LICENSE.txt \
       /usr/share/doc/ffmpeg-shared/LICENSE.txt \
    && ldconfig \
    && rm -rf /tmp/ffmpeg-shared.tar.xz /tmp/ffmpeg-shared-extract \
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
