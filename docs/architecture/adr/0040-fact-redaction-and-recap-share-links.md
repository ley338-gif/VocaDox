# 0040 — Fact-level redaction (evidence preserved) and expiring Recap share links

## Status
Accepted (2026-09-07). Post-GA, roadmap item P3-2 — the final measure of
the 12-item competitive roadmap.

## Context

Two distinct capabilities, delivered together because the roadmap names
them together: "Schwärzung auf Fakten-Ebene bei erhaltener Evidenzkette
und mit Audit-Eintrag, plus ablaufende Freigabe-Links für den Recap."

**Redaction** needed a decision: is this the same thing as the existing
`FactReviewStatus.REMOVED` (Phase 5 Review Wizard — "a human decided
this fact should not appear in the document")? **No.** `REMOVED` means
"this fact is wrong or shouldn't have been extracted" — a correction
concept. Redaction means "this fact is true, evidenced, and correctly
extracted, but must not appear in shared/exported output" — a
disclosure-control concept, orthogonal to correctness. A fact can be
CONFIRMED (genuinely correct) and redacted at the same time.

**Share links** needed a decision about what "expiring" and "public"
actually mean for a codebase where every other endpoint requires a
session — this is the first genuinely unauthenticated REST surface in
VocaDox.

## Decision

**1. Redaction is a new, orthogonal dimension on `ExtractedFact`
(`is_redacted`), not a repurposing of `review_status`.** Toggling it
(`app.intelligence.service.redact_fact`/`unredact_fact`) writes an
immutable `FactRedactionEvent` audit row (mirroring `FactCorrection`'s
own "one row per event, never overwritten" discipline) and never
touches `structured_value`, `corrected_structured_value`, or any
evidence link — nothing about the fact or its evidence chain is ever
deleted or altered, satisfying "erhaltener Evidenzkette" literally.

**2. The blackout lives in one place — `render_fact_statement`
(`app.intelligence.rendering`) — not duplicated per consumer.** That
function is already the single shared renderer for Document composition,
search indexing, and Ask VocaDox citations (established well before this
measure, see the P0-1/P1-1 ADRs). Making it return a fixed placeholder
(`"[Geschwärzt]"`) for a redacted fact, before any category-specific
logic runs, blacks the content out everywhere at once, by construction —
no consumer can forget to check `is_redacted` because none of them
render fact content any other way. The raw `GET .../facts` API
deliberately never calls this function, so the internal, permission-
gated Facts view still shows a reviewer the real content and why it was
redacted (the audit trail) — redaction hides content from *shared
outputs*, never from the people authorized to manage it.

**3. Redaction requires a new, narrowly-granted permission
(`fact:redact`), not `document:edit` or `fact:extract`.** Granted only
to Manager and Reviewer — the same trust level `document:approve`
already requires — not to the standard `User` role. Deciding what must
be hidden from a shared document is a distinct, more consequential
action than composing or extracting one.

**4. Share links are a genuinely new unauthenticated router
(`app.recap.public_router`), never merged into the authenticated
`app.recap.router`.** Every other endpoint in this codebase requires
`Depends(get_current_user)`; keeping the one exception in its own file
makes "this route needs no session" a structural, file-level fact
instead of something to notice line-by-line in a large router. No CSRF
check either — nothing state-changing happens beyond an access counter,
and CSRF protection exists specifically to stop a cross-site request
from using an *authenticated* session it shouldn't have; there is no
session here to misuse.

**5. Authorization is entirely the possession of an unguessable token**
(`secrets.token_urlsafe(32)`, ~256 bits of entropy — the same primitive
`app.identity.sessions.SessionData` already uses for session tokens).
`get_valid_share_link` collapses "doesn't exist" / "expired" / "revoked"
into the same 404, matching `authorize_conversation_access`'s own
never-distinguish-the-reason posture for anything reachable without
normal authorization — a guessed or expired token teaches an attacker
nothing about whether it was ever real.

**6. The link always serves the recap's LIVE current-revision content,
never a frozen snapshot taken at share time.** If the recap is somehow
no longer in an APPROVED revision (a new draft superseded it), the
public endpoint 404s rather than serving stale or unapproved content —
revoking approval takes effect on every outstanding link immediately,
with no separate revocation step needed for that specific case.

**7. Creating a share link requires `recap:approve` (not `recap:read`).**
Sharing something externally, without any access control beyond the
link itself, is at least as consequential as approving it — the same
person trusted to certify the recap's accuracy is the one trusted to
decide it should leave the system.

**8. Phase 14 hardening: the bearer token is creation-only and hash-at-rest.**
The database stores `SHA-256(token)`, while the raw 256-bit value is returned
exactly once by the create endpoint. Listing and revocation require
`recap:approve` and list only metadata, so database read access or the management
API cannot recover a reusable public URL. Public responses use `no-store` and
`no-referrer`, and the production proxy applies a dedicated per-IP limit. Hashing
preserves existing links during upgrade because lookup hashes the presented raw
token; a downgrade cannot reconstruct those raw values and therefore invalidates
their external usability.

## Consequences

- No new dependency (both features use only stdlib primitives —
  `secrets.token_urlsafe`, plain SQLAlchemy models).
- Redaction is fully reversible (`unredact_fact`) and every toggle is
  audited — nothing is a one-way door, matching the "evidence chain
  preserved" framing throughout.
- The public share-link page (`frontend/src/pages/PublicRecapPage.tsx`)
  is the one page in the frontend reachable with no login — deliberately
  minimal, no other conversation data, nothing beyond the recap text and
  its expiry.
- SQLite (this project's test-suite database) round-trips
  `DateTime(timezone=True)` values as naive, unlike Postgres — discovered
  while testing `get_valid_share_link`'s expiry comparison
  (`TypeError: can't compare offset-naive and offset-aware datetimes`).
  Fixed by normalizing a naive read-back value to UTC before comparing,
  documented inline at the one call site that needed it; every write to
  this table already used `datetime.now(UTC)`, so the normalization is
  provably correct, not a guess.
- Rate limiting is implemented at the production reverse proxy. Operators that
  expose the backend without that topology do not receive this control and are
  outside the supported production deployment model.
