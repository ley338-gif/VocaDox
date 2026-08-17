# Security policy

## Reporting a vulnerability

VocaDox is an on-premise product; if you find a security issue, please
report it privately rather than opening a public GitHub issue. Contact the
maintainers directly (see repository owner contact details) with:

- A description of the issue and its potential impact.
- Steps to reproduce (proof-of-concept welcome, exploit code not
  required).
- The version/commit you tested against.

We aim to acknowledge reports within a reasonable timeframe and will work
with you on a coordinated disclosure timeline. Please do not test against
any deployment you don't own or have explicit permission to test.

## Security principles

These hold across every phase of the project, not just Phase 0:

- **On-premise, zero external telemetry by default.** See
  [ADR-0007](docs/architecture/adr/0007-zero-external-telemetry.md). No
  conversation content, transcript, audio, or LLM prompt/completion leaves
  customer infrastructure unless the customer explicitly configures an
  integration to do so.
- **Never log sensitive content.** Transcript text, audio bytes, LLM
  prompts/completions, and secrets must never appear in logs — see
  `docs/security/threat-model.md` §4 and the redaction backstop in
  `backend/app/platform/logging.py`.
- **No path traversal by construction.** All stored media/blobs use
  server-generated UUID keys, never caller-supplied paths — see
  `docs/security/threat-model.md` §2.
- **No shell injection.** Any subprocess invocation (ffmpeg, etc.) uses an
  argument list, never `shell=True` with string-concatenated user input —
  see `docs/security/threat-model.md` §1.
- **Dependency and container hygiene.** Every dependency and container
  image is license-reviewed and tracked in `compliance/`; the same
  standard applies to keeping them patched. `compliance/check_licenses.py`
  runs in CI.
- **Auth by default, not by exception.** Once Phase 1 adds authentication,
  every domain route sits behind it by default (see
  `docs/security/threat-model.md` §5) — health/readiness probes are the
  sole intentional exception.

For the full current threat model, see
[`docs/security/threat-model.md`](docs/security/threat-model.md).
