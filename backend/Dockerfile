# Pinned base image (see compliance/container-inventory.yml for license/digest record).
FROM python:3.11.10-slim-bookworm@sha256:840e180ebcc6e5c8efab209c43f5e40fd2af98cb49db5c7103c90539c56bb30e

WORKDIR /app

# Apply Debian's within-release security patches to every OS package
# already present in the base image (openssl, libgnutls, krb5, pam,
# sqlite, ...). Added during Phase 0 remediation after a Trivy scan of the
# built image found dozens of HIGH/CRITICAL CVEs in the base image's OS
# layer that Debian had already backported fixes for — this was simply a
# stale base-image snapshot, not anything about our own dependencies.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Same idea for pip's own bundled setuptools/wheel (installed by
# ensurepip when the base image was built, independent of the
# setuptools>=83.0 build-system requirement in pyproject.toml, which only
# governs the isolated PEP 517 build environment — not what's left sitting
# in the image's global site-packages).
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    # Also remove the *dormant* old setuptools wheel bundled inside
    # ensurepip's own bootstrap files — it's never executed (ensurepip
    # only runs when explicitly invoked, which we never do), but a Trivy
    # scan still flags its on-disk presence, so delete it rather than
    # carry a stale finding for a file with no code path that runs it.
    && rm -rf /usr/local/lib/python3.11/ensurepip/_bundled

# No `apt-get install build-essential` here (deliberately) — verified
# during Phase 0 remediation that every runtime dependency (asyncpg
# included) installs from prebuilt manylinux wheels on this base image, so
# no C/C++ toolchain is needed. Pulling in build-essential previously
# dragged linux-libc-dev + gcc/binutils/perl's toolchain into the final
# image and was directly responsible for the large majority of
# CRITICAL/HIGH findings in the Trivy image scan (see
# compliance/container-inventory.yml and PHASE_0_VALIDATION_REPORT.md,
# Security Findings). If a future dependency ever needs to compile from
# source, do it in a separate builder stage and copy only the built
# artifact into this final image — never leave the toolchain itself here.

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 vocadox
USER vocadox

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
