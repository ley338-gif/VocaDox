# Pinned base image (see compliance/container-inventory.yml for license/digest record).
# Debian trixie (13), not the originally scaffolded bookworm (12): a Trivy
# scan during Phase 0 remediation found several CRITICAL CVEs (perl-base,
# libsqlite3-0, zlib1g) in bookworm with no fix backported to bookworm at
# all (confirmed via the Debian security tracker — bookworm-security still
# shows "vulnerable" for these, e.g. CVE-2026-53615/util-linux; sqlite3's
# CVE-2025-7458 is marked "no-dsa", i.e. Debian decided not to backport a
# fix to bookworm). trixie carries fixed package versions for all of them.
FROM python:3.11-slim-trixie@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7

WORKDIR /app

# Apply Debian's within-release security patches to every OS package
# already present in the base image (openssl, libgnutls, krb5, pam,
# sqlite, ...). Added during Phase 0 remediation after a Trivy scan of the
# built image found dozens of HIGH/CRITICAL CVEs in the base image's OS
# layer that Debian had already backported fixes for — this was simply a
# stale base-image snapshot, not anything about our own dependencies.
#
# Then remove perl-base entirely. It's marked "Essential" by Debian
# packaging convention (hence --allow-remove-essential), but nothing in
# this image's actual runtime path uses it — our application is a plain
# Python ASGI process with no shell scripts, package-manager maintainer
# scripts, or anything else that invokes perl after the image is built.
# It was also the source of every remaining CRITICAL Trivy finding on this
# image (four 2026 perl CVEs with no upstream fix yet on ANY Debian
# release, verified against both bookworm and trixie) — verified after
# removal that `python3`/`pip` still work correctly (see the `docker build`
# + smoke-test log in PHASE_0_VALIDATION_REPORT.md).
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get remove -y --purge --allow-remove-essential perl-base \
    && apt-get autoremove -y \
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

# Phase 2: media_storage_root/upload_temp_dir default to ./data/media and
# ./data/tmp-uploads (relative to WORKDIR /app). /app itself is owned by
# root (everything above was COPY'd/built before this point) so the
# non-root `vocadox` user can't mkdir under it at runtime without this —
# found via a real fresh-install run (`docker compose down -v && build
# --no-cache && up -d`), not assumed. The actual persistent data lives in
# a named volume mounted at /app/data (see deploy/docker-compose.yml), so
# this only needs to own the mount point, not pre-populate real content.
RUN mkdir -p /app/data/media /app/data/tmp-uploads && chown -R vocadox:vocadox /app/data

USER vocadox

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
