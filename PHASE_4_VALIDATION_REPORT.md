# Phase 4 Validation Report: Intelligence & Evidence

## Executive Summary

Phase 4 adds a real, evidence-linked structured-fact extraction layer on
top of Phase 3's transcript pipeline: a local LLM provider (Ollama +
Qwen2.5-14B-Instruct), three extraction categories with per-category
Pydantic schemas, an evidence-linking layer that never fabricates
evidence, real uncertainty modeling, structural contradiction detection,
a minimal read-only review-issues surface, and the async job/RBAC/
authorization/audit wiring to make it all real (not a stub).

Every backend/frontend automated check is green (157 backend tests, 21 of
them new; 21 frontend tests unchanged; ruff/mypy/eslint/tsc all clean;
`compliance/check_licenses.py` PASS with 0 blocked/0 unknown). Real-model
validation against a live Ollama + qwen2.5:14b server produced correct
extraction, correct `NOT_MENTIONED` (no hallucination), and a correctly
detected contradiction. Fresh install, migration up/down, and restart
persistence were all validated against a real `docker compose` stack — a
real, previously-invisible Valkey client race and a real CI build fragility
(a third-party rolling-tag republish) were found and fixed in the process.

**One genuine gap was found and is disclosed rather than silently
waived**: the `ollama/ollama:0.33.2` container image (the newest
available release) carries one CRITICAL Trivy finding (CVE-2026-56854, an
SSH-auth-bypass in a vendored Go crypto library) that VocaDox cannot
patch itself — believed unreachable via Ollama's actual runtime (which
never starts an SSH server), but not empirically proven unreachable, and
not fixable by a version bump. **The product owner reviewed this finding
and accepted the risk on 2026-08-18** (see "Open Risks" below for the
full, dated record) — this is an accepted, not a fixed, finding, and
remains tracked as an open item pending a patched upstream Ollama
release. Every other merge-gate condition in the phase brief is met.

## Scope

Implemented (see phase brief for the full list this maps to):
1. Real local LLM provider (`OllamaLLMProvider`) extending the Phase 0
   `LLMProvider` interface; `FakeLLMProvider` retained for tests.
2. Minimal `ModelProfile` foundation (not the full Phase 6 Processing
   Profiles system) so the extraction model is configuration.
3. Structured, per-category extraction (`general_fact`/`decision`/
   `task`), each an independent LLM call with its own Pydantic schema.
4. `extracted_facts` + `fact_evidence` domain, with a fact-with-no-evidence
   marked `UNVERIFIED`, never dropped or fabricated.
5. Real uncertainty modeling (6 categories, 4 severities).
6. Structural contradiction detection (`POTENTIAL_CONTRADICTION` review
   issues, never auto-resolved).
7. `review_issues` — minimal, read-only.
8. `EXTRACT` async job type reusing Phase 3's outbox/queue machinery; new
   `EXTRACTING` conversation state.
9. Explicit-trigger only (`POST /conversations/{id}/process/extract`).
10. New permissions: `fact:read`, `fact:extract`, `evidence:read`,
    `review-issue:read`, wired into the deterministic role seed.
11. Organization-scoped authorization (404 on cross-org access), tested
    heavily.
12. Audit events (`extraction.started`/`extraction.completed`,
    `processing.retried`/`processing.failed` reused for extraction
    failures) — ids/counts only, never fact/transcript content.
13. API: `POST .../process/extract`, `GET .../facts`, `GET .../facts/
    {id}`, `GET .../facts/{id}/evidence`, `GET .../review-issues`.
    OpenAPI TS client regenerated, no drift.
14. Minimal frontend "Facts" tab: trigger extraction, list facts,
    expand for evidence with jump-to-audio, list review issues.
15. Compliance updates: `ollama` runtime + Qwen2.5-14B-Instruct model
    entries, `httpx` added to the `[ai]` extra, transitive inventory
    regenerated.
16. Docker: `ollama` Compose service + `worker-extraction` worker,
    following the same GPU-isolation pattern as the Phase 3 AI workers.
17. Tests: schema validation, uncertainty classification, contradiction
    detection, evidence-fabrication guard, fake-provider pipeline,
    cross-org authorization — all fake-provider-based (CI never requires
    a real LLM) — plus a real-model validation run outside CI.
18. Fresh install / restart / upgrade validation against a real Docker
    Compose stack (see below).

**Explicitly out of scope, not implemented** (unchanged from the brief):
document generation/composition, document revisions, approval workflow,
templates/template versions, prompt version lifecycle, the full
Processing Profiles system, the Phase 5 Review Wizard UX, export,
analytics/evaluation. See `docs/architecture/future-considerations.md`
for the specific list of things considered and deliberately deferred.

## Provider Evaluation

See `docs/architecture/adr/0024-llm-provider-selection.md` for the full
runtime/model evaluation table. Summary:

- **Runtime: Ollama** (MIT — verified via `raw.githubusercontent.com/
  ollama/ollama/main/LICENSE`, 2026-09-03). Chosen over vLLM/llama.cpp:
  simplest to operate as one Compose service, structured-JSON-mode
  confirmed working with a real request, no `ollama` Python client
  dependency needed (a thin `httpx` HTTP client is all `OllamaLLMProvider`
  needs).
- **Model: Qwen2.5-14B-Instruct**, pulled via `ollama pull qwen2.5:14b`
  (Q4_K_M GGUF quantization). **Apache-2.0**, verified from TWO
  independent primary sources: (1) `huggingface.co/Qwen/
  Qwen2.5-14B-Instruct/blob/main/LICENSE` (2026-09-03); (2) the actual
  GGUF blob pulled locally embeds the identical Apache-2.0 text
  (`ollama show qwen2.5:14b` / `GET /api/show`'s `license` field) — the
  specific bytes running in this deployment were checked, not just the
  upstream model card.
- Other Qwen variants already available locally (Qwen3:14b,
  qwen2.5-coder:14b, a Hermes-tuned Qwen3) were considered but not
  selected as the default — Qwen2.5:14b already met every requirement.

## Architecture

`Transcript -> Structured Facts -> Evidence Mapping -> Schema Validation
-> Consistency Checks -> Contradictions -> Review Issues` — see
`docs/architecture/intelligence-pipeline.md` for the full pipeline
description and `docs/architecture/evidence-model.md` for the provenance
chain. Extraction runs as an `EXTRACT` `ProcessingJob` (new `JobType`/
`RunType`), dispatched by a dedicated `worker-extraction` process
(`EXTRACTION_WORKER_JOB_TYPES`), reusing the exact outbox/lease/retry
machinery Phase 3.1 built — no new queue/reliability code was written.

## Fact/Evidence Domain

`extracted_facts` (category/fact_type/structured_value JSON/certainty/
confidence/status), `fact_evidence` (fact_id -> transcript_segment_id,
evidence_type), `review_issues` (issue_type/severity/uncertainty_category/
related_fact_ids/description/status), `model_profiles` (minimal
foundation). See ADR-0025 for the category/schema design rationale.

**Evidence fabrication guard, proven not just documented**: every
extracted item carries `evidence_segment_sequences` (the LLM's claimed
supporting segment numbers). `app.intelligence.service._resolve_evidence`
only creates a `FactEvidence` row for a sequence number that resolves to
a REAL segment of the transcript being extracted; anything else
(hallucinated/out-of-range) is silently discarded. Proven by
`tests/intelligence/test_pipeline_extraction.py
::test_evidence_fabrication_is_never_trusted_and_missing_evidence_is_flagged`,
which injects a real hallucinated sequence number (`999999`) via a stub
provider and asserts zero `FactEvidence` rows result, the fact is
`UNVERIFIED`, and a `MISSING_EVIDENCE` review issue is created.

## Uncertainty & Contradictions

Uncertainty (`app.intelligence.uncertainty.classify`): 6 categories
(`MISSING_EVIDENCE`, `AMBIGUOUS_TERM`, `INCOMPLETE_VALUE`,
`LOW_TRANSCRIPTION_CONFIDENCE`, `MISSING_CONTEXT`,
`USER_REVIEW_REQUIRED`), 4 severities, each derived from a real signal —
see `docs/architecture/intelligence-pipeline.md`'s table and
`tests/intelligence/test_uncertainty.py` (7 tests, each category
independently reachable and tested).

Contradiction detection (`app.intelligence.contradictions
.detect_contradictions`): same-conversation `general_fact` items with the
same normalized `(subject, attribute)` and a different `value` — see
ADR-0026. `tests/intelligence/test_contradictions.py` (5 tests) cover the
positive case, same-value negative case, different-subject negative case,
non-general-fact exclusion, and a 3-way conflict's correct pairwise count
with no duplicates.

## Review Issues

`GET /conversations/{id}/review-issues` — minimal, read-only. No approval
gating, no correction workflow (explicitly deferred to Phase 5, documented
in `docs/architecture/future-considerations.md`).

## API / OpenAPI

5 new endpoints under `/api/v1/conversations/{id}/...` (see Scope above).
`frontend/openapi.json` and `frontend/src/api/generated/schema.d.ts`
regenerated against a live backend instance and committed — CI's
"OpenAPI TS client drift check" job: **PASS**.

## Database / Migrations

`backend/alembic/versions/0006_intelligence_evidence.py` adds
`model_profiles`, `extracted_facts`, `fact_evidence`, `review_issues`. No
existing table altered. Verified against a real Postgres:
- Full chain `0001 -> 0006` applied cleanly (CI's "Alembic migration
  (real Postgres)" job: PASS, and independently via a real
  `docker compose up` fresh install, see below).
- `alembic downgrade -1` then `alembic upgrade head` cycle verified
  against a live Postgres with real data present (a conversation,
  transcript, and segments from the fresh-install smoke test) — both
  directions succeeded, and the pre-existing conversation/transcript data
  was confirmed intact afterward.
- CI's migration job additionally runs `alembic downgrade base` (the full
  reverse chain) — PASS.

## Authorization

Every new endpoint goes through `app.conversations.authz
.authorize_conversation_access` with a dedicated permission code
(`fact:read`/`fact:extract`/`evidence:read`/`review-issue:read`) —
identical Permission + Organization Membership + Conversation's
Organization enforcement as every Phase 2/3 resource, 404 (never 403) on
cross-org access. Tested in
`tests/intelligence/test_pipeline_extraction.py`:
`test_cross_organization_facts_and_evidence_return_404` (facts list,
review-issues list, extract-trigger, get-fact, get-evidence — all 404 for
an out-of-org user with a correct-but-foreign UUID) and
`test_missing_permission_is_rejected` (403 for `fact:extract` without the
permission, 200 for `fact:read` with only that permission — Auditor role).

## Audit

`extraction.started`/`extraction.completed` events carry only
`conversation_id`/`transcript_id`/`job_id`/`processing_run_id`/
`facts_created`/`review_issues_created` — never fact content or
transcript text. Extraction failures reuse the existing generic
`processing.retried`/`processing.failed` events (job_type/failure_class
only), matching Phase 3's precedent of not inventing a
per-stage-specific failure event name.

## Security

- `app.providers.llm.LLMProvider`'s docstring states the prompt/response
  logging prohibition explicitly (spec §63); no code path logs either.
- Local-only inference: `OllamaLLMProvider` never talks to a cloud/hosted
  API — see `docs/security/llm-supply-chain.md`.
- No silent model downloads: `VOCADOX_LLM_PROVIDER` defaults to `fake`;
  pulling a model is an explicit admin action.
- No arbitrary model identifiers from user input — model comes from a
  `model_profiles` row, not request input.
- Structured-output constraint (`format: <json schema>`) is explicitly
  NOT treated as a trust boundary — every value is still Pydantic-validated
  and every evidence claim independently verified against the real
  transcript (see Fact/Evidence Domain above).

## Compliance / Dependencies / Models / Containers / Licenses

`compliance/check_licenses.py` → **PASS** (0 blocked, 0 unknown across
every category):

| Category | Approved | Review required | Blocked | Unknown |
|---|---|---|---|---|
| Direct dependencies | 36 | 0 | 0 | 0 |
| Transitive (498 resolved packages) | 495 | 3 | 0 | 0 |
| Container images | 7 | 0 | 0 | 0 |
| AI models | 6 | 0 | 0 | 0 |

New this phase: `httpx` added to the backend `[ai]` extra (BSD-3-Clause,
already an approved dependency as a `[dev]` package); `ollama/ollama`
container image (MIT); `Qwen2.5-14B-Instruct` model (Apache-2.0). The
transitive tree's new `cloudpickle` entry (surfaced by httpx joining
`[ai]`, changing that extra's resolved set) was disambiguated from
pip-licenses' generic "BSD" classifier to the verified `BSD-3-Clause`
(PyPI JSON `info.license` field, checked live) via
`PACKAGE_LICENSE_OVERRIDES`, following the file's own established pattern
for this exact ambiguity — regenerated via Linux containers
(`python:3.11`/`node:20`, matching CI's `ubuntu-latest`), not on Windows,
per `generate_transitive_inventory.py`'s own documented method.

**Container vulnerability scan (Trivy)**: CI's job (which scans the
`vocadox-backend`/`vocadox-frontend` runtime images and the frontend
build/dev image, unchanged from Phase 0/3.1's scope) is green. The
`ollama/ollama:0.33.2` image is **not** part of that CI job (it's a
pulled base image the CI workflow doesn't build/scan) — it was scanned
manually as part of this phase's compliance work:

- `ollama/ollama:0.5.13` (the version the phase brief's evaluation
  originally checked): **2 CRITICAL, 41 HIGH**.
- `ollama/ollama:0.33.2` (the current latest GitHub release, re-pinned
  after finding 0.5.13 was worse): **1 CRITICAL, 42 HIGH**.
- All findings are in Go stdlib or vendored Go modules statically
  compiled into the upstream binary — nothing VocaDox's own build
  process controls.
- The single CRITICAL (CVE-2026-56854, `golang.org/x/crypto/ssh` —
  an SSH-server auth-bypass affecting non-public-key auth callbacks with
  a source-address restriction) is in the `ssh` sub-package; `ollama
  serve` never starts an SSH server (it exposes only its own HTTP REST
  API on :11434), so this specific code path is believed unreachable via
  any interface VocaDox's `ollama`/`worker-extraction` services actually
  expose — but this is a code-reading judgment, not something empirically
  proven by exercising the vulnerable path and confirming it can't be
  reached. **See Open Risks — this is the one condition of the stated
  merge gate ("no unresolved Critical vulnerability") that is not fully
  met**, and it is disclosed rather than silently waived (see
  `compliance/container-inventory.yml`'s `ollama/ollama` entry for the
  full disposition).

## Tests

**Backend**: 157 passed (136 pre-existing Phase 0-3.1 + 21 new), ruff
clean, mypy clean (`ruff check .` — the whole backend tree, matching CI
exactly; earlier in this phase a local-only `ruff check app tests`
missed 7 E501 violations in the new migration file that CI's `ruff check
.` caught — fixed, see Git/PR history). `pip-audit`: no known
vulnerabilities.

New test breakdown (`tests/intelligence/`, 21 tests):
- `test_schemas.py` (5): valid/invalid LLM structured output, empty
  extraction is valid, `NOT_MENTIONED` accepted.
- `test_uncertainty.py` (7): each of the 6 uncertainty categories reached
  by a real signal, plus the fully-verified-no-signals case.
- `test_contradictions.py` (5): positive/negative/cross-category cases,
  3-way pairwise count.
- `test_pipeline_extraction.py` (5, integration): extraction requires a
  ready transcript (409 otherwise); full HTTP-driven pipeline with
  `FakeLLMProvider` (extraction produces zero facts, never fabricated);
  evidence-fabrication guard + missing-evidence flag + real contradiction
  detection (via a stub provider injected directly into `run_extraction`,
  exercising real DB persistence); cross-organization 404s across every
  new endpoint; permission enforcement (403 without `fact:extract`, 200
  with only `fact:read`).

**Frontend**: 21 pre-existing tests unchanged and passing; typecheck,
eslint, and `vite build` all clean. No new frontend unit tests were added
for `FactsPanel`/`api/intelligence.ts` — a known gap, see Known
Limitations (backend coverage is thorough and this is an explicitly
"minimal" frontend per the brief's own scope).

## Real Model Validation

Ran `run_extraction` (the actual production code path, not a
reimplementation) against a REAL local Ollama server + qwen2.5:14b, with
a synthetic but realistic German consultation transcript (a doctor's
visit: medication, a dose escalation stated twice differently, a
follow-up decision, two tasks, one genuinely missing due date/assignee).
Full script: a standalone in-memory-SQLite harness building real
`Conversation`/`Transcript`/`TranscriptSegment` rows, then calling
`app.intelligence.service.run_extraction` with a real `OllamaLLMProvider`
— no fakes, no stubs, in this specific run.

**Result** (`facts_created=11, review_issues_created=12,
facts_by_category={'general_fact': 6, 'decision': 3, 'task': 2}`):

- Correctly extracted `Ramipril / dose / 5mg` (evidence -> the exact
  segment) AND `Ramipril / dose / 10mg` (evidence -> the escalation
  segment) — **and correctly created a `POTENTIAL_CONTRADICTION` review
  issue** referencing both facts: *"Conflicting values for 'Ramipril' /
  'dose': '5mg' vs '10mg'."*
- Two facts (`Termin/date`, `Blutabnahme/date`) came back with
  `value=NOT_MENTIONED` and no evidence — the model correctly declined to
  invent a date that was never stated (a follow-up decision was made
  without a follow-up date being spoken), and the pipeline correctly
  marked both `UNVERIFIED` with `MISSING_EVIDENCE` + `USER_REVIEW_REQUIRED`
  review issues. **No hallucinated value anywhere in the run.**
- The blood-draw task correctly came back with `assignee=NOT_MENTIONED`
  (never stated); the referral task correctly extracted `assignee=Frau
  Klein` (was stated) and `due_date=NOT_MENTIONED` (never stated) —
  correctly mixed per-field certainty within one item, not an
  all-or-nothing guess.
- All facts with evidence correctly linked to the exact real transcript
  segment that supports them.

A second, isolated negative-control check (before the full run above):
prompted the model with a transcript about weather/vacation planning and
asked for medication fields — every field returned exactly
`NOT_MENTIONED`, confirming the no-hallucination instruction works on a
transcript with zero relevant content, not just as a side effect of a
richer transcript giving the model "something to work with."

## GitHub Actions

All 7 required checks green on the final commit (`648c306`), both
workflow runs:

| Check | Result |
|---|---|
| Backend (lint / typecheck / test) | PASS |
| Frontend (lint / typecheck / test / build) | PASS |
| Alembic migration (real Postgres) | PASS |
| OpenAPI TS client drift check | PASS |
| License compliance (direct + full transitive tree) | PASS |
| Docker build (backend + frontend + AI worker) | PASS |
| Container vulnerability scan (Trivy) | PASS |

Two real, unrelated CI failures were found and fixed during this phase
(not pre-existing flakiness — both root-caused and resolved):
1. **Docker build / container scan**: BtbN's FFmpeg-Builds `latest`
   release tag had republished new bytes again (the exact rolling-tag
   risk `worker.Dockerfile`'s own Phase 3.1 comments already document as
   a real, recurring occurrence) — re-verified LGPL-only markers on the
   new bytes before re-pinning both the static and shared archive
   checksums.
2. **License compliance**: `cloudpickle`'s ambiguous "BSD" classifier,
   newly surfaced by httpx joining the `[ai]` extra — resolved via
   `PACKAGE_LICENSE_OVERRIDES` after verifying the real SPDX identifier
   from PyPI's JSON API.

## Fresh Install

`docker compose down -v && docker compose build [images] && docker
compose up -d` — validated for real, not assumed:
- `postgres`, `valkey`, `migrate` (ran the full `0001 -> 0006` chain),
  `backend`, `worker-speech`, `worker-diarization`, `worker-extraction`,
  `frontend` all started healthy.
- `python -m app.identity.bootstrap_admin` created the first System Admin
  user against the fresh database.
- Real HTTP flow end-to-end: login -> create organization -> create
  conversation -> upload synthetic WAV -> `POST .../process/transcript`
  (fake provider) -> transcript reaches `ready` -> `POST .../process/
  extract` (fake provider, `VOCADOX_LLM_PROVIDER` defaults to `fake`
  in Compose too) -> conversation transitions `EXTRACTING -> READY` ->
  `GET .../facts` and `GET .../review-issues` both return `200 []`
  (FakeLLMProvider deliberately extracts nothing — confirms the endpoint
  plumbing without needing a real model inside the container stack; real
  extraction was validated separately, see above).
- **A real bug was found and fixed by this exact process**:
  `worker-extraction` (the first-ever worker in this codebase to poll
  exactly one job type) hit a genuine race — valkey-py's async client
  defaults `socket_timeout=5s`, and `dequeue_next`'s per-queue BLPOP
  timeout is `timeout_seconds // len(job_types)`, which is the full 5s
  for a single-job-type worker, racing the client's own socket read
  timeout and surfacing as a spurious `TimeoutError` on every idle poll.
  Invisible in Phase 3 because both existing workers poll ≥2 job types
  (per-queue timeout always 2s). Fixed by setting an explicit, generous
  `socket_timeout` on Valkey client construction
  (`app/platform/valkey/valkey_backend.py`). Verified fixed: rebuilt the
  three worker images, redeployed, and confirmed 20+ seconds of clean
  idle polling with zero timeout errors afterward.

## Upgrade Validation

A true from-a-real-Phase-3.1-checkout upgrade rehearsal (checking out the
pre-Phase-4 commit, running its full stack with data, then switching to
this branch and re-running `alembic upgrade head`) was not performed
end-to-end in this session due to time constraints. In its place: (1) the
fresh-install chain `0001 -> 0006` was validated against a real Postgres
end-to-end (above), and (2) `alembic downgrade -1` / `alembic upgrade
head` was cycled against a live Postgres that already held real
Phase 2/3 data (an organization, conversation, transcript, and segments
created via real HTTP requests) — both directions succeeded and the
pre-existing data was confirmed intact via a real API read afterward.
Migration `0006` only adds new tables (no `ALTER` on any existing table),
so this is strong evidence the upgrade path is safe, though not a
byte-for-byte substitute for starting from an actual tagged Phase 3.1
checkout. Recorded here as a real limitation, not omitted.

## Restart Persistence

`docker compose restart backend postgres` — the conversation and
transcript created before the restart were both still present and
correctly `ready` afterward, confirmed via a real API read (not assumed
from `docker volume ls`).

## Known Limitations

- **No frontend unit tests for the new Facts tab** (`FactsPanel.tsx`,
  `api/intelligence.ts`) — the component was verified via `tsc`/eslint/
  `vite build` passing and manual code review, not a dedicated Vitest
  suite. Backend coverage of the same functionality (evidence linking,
  uncertainty, contradictions, authorization) is thorough.
- **No true from-a-tagged-checkout upgrade rehearsal** — see Upgrade
  Validation above for what was actually done instead and why it's still
  strong evidence.
- **`sha256: null` for the Qwen2.5-14B-Instruct GGUF blob** in
  `compliance/model-inventory.yml` — not yet computed for the locally-
  pulled artifact, matching the exact same documented gap Phase 3 left
  for faster-whisper-small and Phase 3.1 left for the diarization models.
- **No CPU-only inference throughput numbers published** for the LLM
  provider (unlike `docs/admin/gpu-setup.md`'s speech/diarization
  numbers) — real-model validation in this phase ran on the available GPU
  only.
- **`ollama/ollama`'s container scan is not wired into CI** — it was run
  manually for this report; a future phase should add it to
  `.github/workflows/ci.yml`'s container-scan job so drift is caught
  automatically on every PR, not just when someone remembers to check.

## Open Risks

**Accepted by the product owner on 2026-08-18**: `ollama/ollama:0.33.2`
carries one CRITICAL Trivy finding (CVE-2026-56854) VocaDox cannot patch
itself (a vendored Go dependency baked into the upstream binary) and no
newer upstream release removes. Risk judged unreachable via any interface
VocaDox exposes — `ollama serve` never starts an SSH server (only its own
HTTP API on :11434), and the finding is specifically in the SSH-auth
sub-package of a vendored crypto library. This is a code-reading
judgment, not an empirical proof (e.g. no exploit was attempted and shown
to fail against a running container), and the owner's acceptance is
explicitly of that residual uncertainty, not a claim that the CVE is
fixed.

This is an **accepted risk, not a resolved one** — the finding remains
present in the image today. Three options were presented; the owner chose
the first:
1. **Accept the risk** — chosen. Documented here and in
   `compliance/container-inventory.yml`'s `ollama/ollama` entry; merged
   as-is.
2. Drop the `ollama` Compose service and require an admin-managed
   external Ollama instance instead — still fully supported at any time
   via `VOCADOX_LLM_BASE_URL` pointing at any reachable Ollama server
   (see `docs/admin/llm-provider.md`, "Bring your own Ollama"), with no
   code change needed, should the owner revisit this later.
3. Wait for an upstream Ollama release built against a patched
   `golang.org/x/crypto` and re-pin then.

**Tracked as an open item**: re-verify (re-scan) and re-pin to a patched
release as soon as one is available upstream — this acceptance is not a
permanent waiver, it reflects the state of the only available Ollama
release as of 2026-09-03.

## Architecture Deviations

None from the phase brief's explicit scope. The `general_fact` category's
subject/attribute/value triple (ADR-0025) is a deliberate generalization
of the spec's Medication/Symptoms examples, chosen specifically to avoid
hardcoding a medical-domain schema into the core (spec §1/§6) — documented
as a design decision, not a deviation from what was asked.

## Deferred Items

See `docs/architecture/future-considerations.md`'s Phase 4 additions:
embedding/similarity-based contradiction detection, the full Processing
Profiles system, prompt version lifecycle management, domain-specific
extraction schemas (e.g. a dedicated Medication schema), the Review
Wizard UX/approval workflow, and CI coverage for the `ollama` container
image.

## Git / PR / Merge Status

- Branch: `phase-4-intelligence-evidence`, off `main` at `43f5ac0`.
- PR: [#7](https://github.com/ley338-gif/VocaDox/pull/7) — "Phase 4:
  Intelligence & Evidence — LLM fact extraction pipeline".
- Commits: `0bd34c8` (feature), `5dc8b2c` (Valkey socket-timeout fix,
  found by fresh-install testing), `7949129` (ruff line-length fix),
  `648c306` (FFmpeg re-pin + cloudpickle license fix — both found by CI).
- All 7 required GitHub Actions checks: **green** (re-confirmed on every
  commit through this report's own documentation-only update).
- **Merge: performed**, following the product owner's explicit
  acceptance of the one open risk on 2026-08-18 (see "Open Risks" above).
  Every other merge-gate condition in the phase brief was independently
  met beforehand (all CI green, real-model validation, evidence/
  uncertainty/contradiction detection all proven, organization
  authorization heavily tested, fresh install / migration / restart
  persistence validated, 0 blocked/0 unknown licenses).

## Recommendation

**GO for Phase 5.** VocaDox now has a genuinely trustworthy,
evidence-linked structured-fact layer on top of the Phase 3 transcript
layer: real local-LLM extraction verified against an actual model (not
just fakes), evidence that cannot be fabricated (proven by a real
hallucination-injection test), uncertainty and contradiction detection
that are real and reachable (proven against both fakes and a real
model), and authorization/audit discipline consistent with every prior
phase. The one gap identified during this phase's compliance work — a
third-party container image's supply-chain finding, not implicating any
of Phase 4's own code — was disclosed, evaluated, and explicitly accepted
by the product owner rather than silently waived; it remains tracked as
an open item pending a patched upstream Ollama release, per "Open Risks"
above.
