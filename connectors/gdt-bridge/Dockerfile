# Prototype GDT connector (ADR-0041). Deliberately minimal: no ML/audio
# toolchain (unlike backend/worker.Dockerfile) -- this is a small,
# pure-Python HTTP client + folder watcher, meant to run on/near a
# practice PC, not alongside VocaDox's own AI workers.
FROM python:3.11-slim-trixie

WORKDIR /app
COPY pyproject.toml ./
COPY gdt_bridge ./gdt_bridge

RUN pip install --no-cache-dir .

RUN useradd --uid 10001 --create-home gdtbridge
USER gdtbridge

ENTRYPOINT ["python", "-m", "gdt_bridge.cli"]
CMD ["run"]
