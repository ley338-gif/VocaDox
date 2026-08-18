# 0010 — Argon2id (argon2-cffi) for password hashing

## Status
Accepted

## Context
Phase 1 needs to store local user passwords irreversibly. The two realistic
modern candidates are `argon2-cffi` (Argon2, specifically Argon2id via its
default `PasswordHasher` profile) and `bcrypt`.

## Decision
Use `argon2-cffi` (PyPI, MIT license — confirmed live against the PyPI
JSON API, recorded in `compliance/dependency-inventory.yml`; its runtime
transitive deps `argon2-cffi-bindings` (MIT), `cffi` (MIT-0), and
`pycparser` (BSD-3-Clause) are all already-approved licenses — see
`compliance/dependency-inventory-transitive.yml`).

Argon2id is the current OWASP Password Storage Cheat Sheet default
recommendation: it won the 2015 Password Hashing Competition, is
memory-hard (resists cheap GPU/ASIC parallelization far better than
bcrypt's fixed, comparatively small memory footprint), and `argon2-cffi`
is actively maintained (https://github.com/hynek/argon2-cffi) with sane
built-in defaults (`argon2.PasswordHasher()` picks a reasonable
time/memory/parallelism cost and self-reports via
`check_needs_rehash()` when those defaults are later strengthened).

## Alternatives considered
- **bcrypt.** Also a reasonable, widely-used choice (Apache-2.0, would
  also have passed license review) but not memory-hard — cheaper to
  attack at scale with modern hardware than Argon2id at equivalent
  configured cost, and OWASP now lists it as the second choice, after
  Argon2id specifically. No compelling reason favored it here.
- **PBKDF2 / plain SHA-256+salt.** Rejected outright: not memory-hard,
  explicitly discouraged by OWASP except as a FIPS-mandated fallback,
  which doesn't apply here.

## Consequences
- `app.identity.passwords` is the single module allowed to hash/verify
  passwords; the rest of the codebase depends on `hash_password` /
  `verify_password` / `needs_rehash`, not on `argon2` directly.
- `MIN_PASSWORD_LENGTH = 12` is a floor enforced at hash time (`ValueError`
  below that), not a full password-strength policy (dictionary/breach
  checks are out of scope for Phase 1 — see
  `PHASE_1_VALIDATION_REPORT.md`, Deferred Items).
- Passwords are never logged: the sensitive-key redaction already in
  `app/platform/logging.py` (ADR-driven, Phase 0) covers accidental
  `password=`-style log kwargs, and no Phase 1 code path passes a raw
  password to the logger.
