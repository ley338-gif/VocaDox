# Prototype GDT connector (ADR-0041). Deliberately minimal: no ML/audio
# toolchain (unlike backend/worker.Dockerfile) -- this is a small,
# pure-Python HTTP client + folder watcher, meant to run on/near a
# practice PC, not alongside VocaDox's own AI workers.
FROM python:3.11-slim-trixie@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7

WORKDIR /app
ENV PATH="/app/.venv/bin:${PATH}"
ARG PIP_VERSION=26.2.1
ARG SETUPTOOLS_VERSION=84.0.0
ARG WHEEL_VERSION=0.46.3
ARG UV_VERSION=0.12.12

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get remove -y --purge --allow-remove-essential perl-base \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      "pip==${PIP_VERSION}" "setuptools==${SETUPTOOLS_VERSION}" "wheel==${WHEEL_VERSION}" \
    && rm -rf /usr/local/lib/python3.11/ensurepip/_bundled

COPY pyproject.toml uv.lock ./
COPY gdt_bridge ./gdt_bridge

RUN pip install --no-cache-dir "uv==${UV_VERSION}" \
    && uv sync --locked --no-dev --no-editable \
    && pip uninstall -y uv \
    && rm -rf /root/.cache/uv

RUN useradd --uid 10001 --create-home gdtbridge
USER gdtbridge

ENTRYPOINT ["python", "-m", "gdt_bridge.cli"]
CMD ["run"]
