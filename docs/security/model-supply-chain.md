# Model supply-chain security

## Pinned revisions, not floating tags

Every model VocaDox installs is pinned to a specific Hugging Face
**revision (commit hash)**, never a branch name or floating tag — see
`compliance/model-inventory.yml` and `app/cli/install_models.py`'s
`PROFILES` dict. If the upstream repo publishes new weights under the
same name, VocaDox keeps using the pinned revision until an admin
deliberately updates the pin (a reviewed code change, not an automatic
pull).

## No arbitrary user-specified model URLs

`install_models.py` only knows about the profiles hardcoded in its
`PROFILES` dict — there is no API parameter or CLI flag that accepts an
arbitrary Hugging Face repo ID or URL from a caller. Adding a new model
requires a code change (and, per this document's process, a fresh
license/provenance review), not a runtime input.

## Admin-only installation

Model installation is a CLI command run inside the worker
container/environment (`docker compose run --rm worker-speech python -m
app.cli.install_models ...`) — there's no API endpoint that triggers a
model download, gated or otherwise. This is a deliberate boundary: an
authenticated but non-admin application user can never cause a worker to
reach out to the internet.

## Token handling

`VOCADOX_HUGGINGFACE_TOKEN` (or the `--token` CLI flag) is read **only**
by `install_models.py` at install time. It is never:
- read by the API or the worker's normal job-execution path,
- persisted to the database,
- included in any audit log, application log, or error message,
- exposed via any HTTP endpoint.

## Integrity verification

Current: revision pin (commit hash) + a post-download marker-file-presence
check (`_is_installed`). This detects a truncated/failed download but is
**not** cryptographic signature verification of the downloaded weights —
documented as a known limitation (see ADR-0018). A compromised upstream
repo serving different bytes under the same pinned revision hash is not
something Hugging Face's revision model itself defends against beyond
git's own content-addressing guarantees for that specific commit.

## FFmpeg binary integrity

The LGPL FFmpeg binary installed in the worker image is downloaded from a
continuously-updated rolling release and verified against a **pinned
sha256** hash before extraction (`backend/worker.Dockerfile`) — an
upstream change to that release invalidates the hash and fails the build
closed, rather than silently accepting different bytes. See
`docs/architecture/adr/0019-ffmpeg-normalization.md`.
