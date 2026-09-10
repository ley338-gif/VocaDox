# VocaDox threat model

**Status:** Production Readiness 2.0 review, 2026-09-10

**Scope:** current application through Phase 14, including post-GA features

**Method:** trust-boundary review plus targeted abuse cases for authentication,
authorization, uploads, exports/connectors, LLM output, browser storage and operations.

VocaDox processes conversation audio, transcripts, inferred facts, documents and
possibly health-related identifiers. All of these are sensitive. An on-premise
deployment reduces third-party exposure, but does not make authenticated users,
browsers, imported files, configured providers or the local network trusted.

## 1. Trust boundaries and assets

| Boundary | Untrusted input | Primary controls |
|---|---|---|
| Browser → reverse proxy/API | Cookies, JSON, uploads, path/query values | TLS, rate limits, schema/size validation, server-side sessions, CSRF |
| User/service account → organization data | UUIDs, organization/team IDs, scopes | permission checks plus organization/team filtering; indistinguishable 404 across boundaries |
| Public recipient → recap | bearer token in URL | random one-time token, hash at rest, approval, expiry/revocation, no-store, rate limit |
| File → storage/renderers | audio, PNG/JPEG, GDT, ICS | streaming byte caps, magic/decode checks, pixel/ZIP limits, server-generated keys |
| Transcript/facts → LLM | prompt-injection text and provider output | bounded context, structured schemas, evidence resolution, human approval where required |
| VocaDox → webhook/LLM endpoint | administrator-supplied URL | HTTPS, public-IP validation, no redirects/proxy inheritance, time/response limits, network policy |
| Browser → IndexedDB | raw offline recording | per-user ownership binding; browser-profile/device protections remain required |
| Runtime → backup/storage | database, media, embeddings, secrets | explicit host paths, least access, operator encryption/retention and restore procedures |

Highest-value assets are raw audio, transcript and fact content; approved documents
and recaps; patient/external references; voice embeddings; account credentials,
sessions, API keys and webhook secrets; audit and backup data.

## 2. Authentication and authorization

- Local passwords use Argon2id. Login gives the same response for an unknown user,
  a wrong password and an inactive account.
- Sessions are opaque, absolute-expiry, server-side Valkey records. Cookies are
  `HttpOnly`, `SameSite=Lax` and `Secure` in production. Every state-changing
  human-session route requires the session-bound `X-CSRF-Token`.
- Each session captures `users.session_generation`. Password reset and account
  deactivation increment it; every protected request compares it with the current
  database value. Thus all prior sessions fail immediately without a cache scan.
- RBAC checks permission codes, never role names. Conversation access combines the
  permission with organization membership and, where applicable, team scope.
- Service-account keys are `{prefix}.{secret}`. Only the prefix and Argon2id hash
  are stored. Rotation overwrites both and revocation is checked on every request.
  Integration routes additionally enforce a per-route scope and the account's one
  organization. Template enumeration returns only global templates plus that
  organization's templates.
- Production Nginx applies per-IP request limits to the general API and tighter
  limits to login and public recap access. Only Nginx publishes host ports in the
  production Compose topology.

## 3. Public recap boundary

The only intentionally unauthenticated product-data route is
`GET /api/v1/public/recap/{token}`.

- Creating, listing and revoking share links requires `recap:approve` plus normal
  conversation organization/team authorization.
- The 256-bit random bearer token is returned only in the create response. The
  database stores only its SHA-256 digest; later list responses expose metadata,
  never a reusable URL.
- Links expire after at most 30 days, can be revoked immediately, and resolve only
  the current approved recap revision. Missing, expired, revoked and unapproved
  states all return the same 404.
- Responses set `Cache-Control: no-store, private`, `Pragma: no-cache` and
  `Referrer-Policy: no-referrer`. Production Nginx rate-limits the route.

Possession of a valid URL still grants access by design. Recipients can copy or
photograph content after delivery; no technical control can revoke such copies.

## 4. Upload, storage and export handling

- Audio ingestion streams into a controlled temporary file, hashing and enforcing
  the configured maximum before permanent storage. Format detection uses bytes,
  not the supplied MIME type. Original filenames never form storage paths and are
  sanitized before display/header use.
- Avatar and letterhead inputs are capped, fully decoded as PNG/JPEG, bounded to
  10 million pixels and 10,000 pixels per side, orientation-normalized and
  re-encoded. This rejects truncated/polyglot/decompression-bomb inputs and strips
  EXIF/GPS and other metadata. Serving re-checks both the fixed storage namespace
  and image magic, preventing a media key from being read through an avatar/logo
  endpoint.
- `LocalFilesystemStorage` mints UUID filenames, sanitizes namespace segments,
  rejects traversal/absolute forms and verifies the resolved path remains below
  its configured root.
- Document/recap filenames are server-generated UUID/revision values. Text sent to
  ReportLab's markup parser is XML-escaped. GDT field lengths are encoded and
  checked by the line codec.
- The GDT bridge caps inbound files before parsing, rejects symlink/resolved paths
  outside its import directory, requires HTTPS for remote API endpoints, and
  accepts only bare `.gdt`/`.pdf` output names. ZIP bundles must contain exactly
  one of each, with compressed/uncompressed size and ratio limits; archive names
  never become paths without validation.
- ICS import is local to the browser, limited to 2 MiB, bounded by line length and
  event count, and sends only the user-selected conversation title through the
  ordinary create route.

## 5. LLM and evidence boundary

Transcript and document content is adversarial data, not an instruction channel.
Prompts tell providers to use only supplied material, but prompt wording is not the
security boundary; server-side validation is.

- Extraction accepts structured output and resolves claimed evidence only against
  real segments from the active transcript. Document composition is deterministic
  from reviewed facts and uses the centralized redaction-aware renderer.
- Ask retrieves only already-authorized facts. Every statement must cite one or
  more IDs, and all IDs must be in the exact candidate set supplied to the model;
  malformed, uncited or fabricated-ID statements are dropped.
- Protocol output is schema-bound, count/text bounded, restricted to known section
  and item types, and rejected as a whole if any section or item has an empty or
  nonexistent transcript citation. Model-created responsible/due-date wording is
  still human-reviewable output, not an authoritative task assignment.
- Recaps are explicitly labeled AI-generated and cannot be exported or shared until
  a user with `recap:approve` approves the current revision.
- Live drafts are short, provisional, ephemeral and never feed the authoritative
  extraction/document pipeline.
- Prompts, completions, transcript text and raw audio are excluded from logs. The
  JSON formatter redacts sensitive keys as defense in depth.

Citation existence proves provenance, not semantic entailment. Ask/protocol users
must inspect the linked source for consequential decisions; automated semantic
verification remains an open research/quality problem.

## 6. Privacy, retention and deletion

- Privacy-zone transcript segments are excluded before extraction. Redaction is a
  fact state consumed by one renderer used by documents, search, Ask and recap
  input, reducing inconsistent downstream masking.
- Offline recordings remain only in IndexedDB until upload succeeds or the owner
  explicitly confirms deletion after a permanent failure. Each entry is bound to
  the immutable VocaDox user ID; another login on the same browser neither counts
  nor uploads it. Legacy unowned entries are quarantined. Stable local and server
  idempotency keys prevent retry-created duplicate assets.
- Voice embeddings are organization-scoped, not returned by APIs, enrolled only by
  an explicit authorized action and used only for suggestions that require human
  confirmation. Deleting the known-speaker record deletes its embedding.
- Conversation retention cleanup and deletion cover database-owned artifacts and
  stored media. Public share links cascade with their conversation. Audit events
  record identifiers/actions rather than conversation content.
- Backups necessarily contain sensitive database/media state. Production requires
  an explicit host backup path; encryption, access control, off-host copying and
  deletion are operator responsibilities documented in operations guidance.

## 7. Outbound integrations and operational abuse

- Webhook creation/update requires `webhook:write`. Targets must use HTTPS and all
  resolved addresses must be public. The address is revalidated immediately before
  each HTTPS attempt; redirects and environment proxy inheritance are disabled.
  Attempts have a 10-second timeout, capture at most 64 KiB of response text, retry
  on a finite schedule and emit only an allow-list of metadata fields. Payloads are
  HMAC-SHA256 signed with timestamp, event and delivery IDs.
- The production network makes Postgres and Valkey internal-only. Speech,
  diarization and extraction workers receive outbound egress; no database/cache
  port is published. Operators should additionally restrict backend webhook/LLM
  egress at the host/firewall layer.
- Live recording chunks are capped at 25 MiB and API request rates are limited at
  the production proxy. Queue retries and webhook retries are bounded. A single
  media object is capped, though aggregate tenant quotas are not yet implemented.

## 8. Findings from the Production Readiness 2.0 sweep

No Critical finding was identified.

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| PR2-SEC-01 | High | Password reset/deactivation left issued sessions valid | Fixed: database session generation checked on every protected request |
| PR2-SEC-02 | High | Recap list re-exposed bearer tokens under weaker read permission | Fixed: approve-only management, creation-only token, hash at rest, no-cache headers |
| PR2-SEC-03 | High | Avatar/logo loaders could read a known key from another storage namespace | Fixed: strict namespace and image revalidation |
| PR2-SEC-04 | High | GDT response filenames/ZIP members could escape the export directory | Fixed: basename, extension, member-count, size and compression checks |
| PR2-SEC-05 | High | Remote GDT API URL could use cleartext HTTP for a bearer key | Fixed: HTTPS required except explicit localhost development |
| PR2-SEC-06 | Medium | Protocol accepted empty/fabricated citations and unconstrained types/text | Fixed: strict schema bounds and all-or-nothing real-source resolution |
| PR2-SEC-07 | Medium | PNG/JPEG magic-only validation allowed malformed images and retained EXIF | Fixed: bounded full decode and metadata-stripping re-encode |
| PR2-SEC-08 | Medium | Service account could enumerate another organization's templates | Fixed: global plus account-organization filter |
| PR2-SEC-09 | Medium | Offline queue was shared across browser logins | Fixed: immutable user ownership; legacy entries quarantined |
| PR2-SEC-10 | Medium | Login/public/API surfaces lacked production abuse throttling | Fixed: dedicated Nginx zones returning 429 |
| PR2-SEC-11 | Medium | Webhook response read and target age were unbounded | Fixed: delivery-time revalidation, timeout, 64-KiB capture, no redirects/proxy env |
| PR2-SEC-12 | Low | Local ICS and inbound GDT parsing had no explicit file/event caps | Fixed: byte, line and event limits |
| PR2-SEC-13 | Medium | Reference webhook verifier accepted correctly signed replays forever | Fixed: five-minute past/future timestamp tolerance |

## 9. Accepted residual risks and required deployment controls

| Risk | Rating | Acceptance / required control |
|---|---|---|
| Public recap bearer URL can be forwarded by a recipient | Medium | Inherent feature trade-off; short chosen expiry, immediate revocation, approved/minimal content and secure communication channel required |
| DNS rebinding can theoretically occur between validation and socket connect | Medium | Admin-only configuration plus repeated validation; production firewall must block backend access to private/link-local/metadata ranges |
| Raw offline audio is not application-encrypted inside IndexedDB | Medium | Needed for offline recovery; use managed, encrypted devices and separate browser/OS profiles; do not enable on shared unmanaged endpoints |
| Voiceprint similarity threshold is not population-calibrated and embeddings are biometric-like data | Medium | Suggestion only, explicit enrollment/human confirmation; obtain lawful basis/consent and disable/delete where not permitted |
| No aggregate per-user/organization storage quota | Medium | Single-object and permission/rate limits exist; operator monitors storage and restricts upload permission until quotas are added |
| Live whole-prefix retranscription cost grows with recording length | Medium | Auth/permission, 25-MiB request and proxy rate limits; intended for short previews, authoritative pass remains separate |
| Ask citations cannot prove the generated wording is semantically entailed | Medium | IDs are closed-set verified and sources are visible; human review required for consequential use |
| FHIR `DocumentReference` is not validated against an official profile/schema | Low | Base R4 shape only and local export; receiving-system conformance testing required before clinical interchange |
| Backups and configured external LLM providers can expose all in-scope content | High if misconfigured | Operator must encrypt/restrict backups and use an approved private provider with suitable retention/processing terms |
| Nginx per-IP throttling can affect many users behind one NAT | Low | Conservative bursts; tune zones for site topology while preserving tighter login/public limits |

## 10. Review triggers

Repeat this review before adding another unauthenticated route, OAuth/SSO, a hosted
LLM, object storage, a new file parser/renderer, automatic (non-suggested) biometric
identity, write-capable FHIR, public internet exposure, multi-tenant hosting, or a
change to retention/backup semantics. Any new endpoint must state its authentication,
permission, organization/team, CSRF, rate, size and logging behavior in tests.
