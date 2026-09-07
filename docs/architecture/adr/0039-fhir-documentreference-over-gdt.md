# 0039 — One real Fachsystem integration: FHIR DocumentReference over GDT

## Status
Accepted (2026-09-07). Post-GA, roadmap item P3-1.

## Context

`docs/architecture/future-considerations.md`'s Phase 10 notes deliberately
documented four future adapters (FHIR/HL7, PVS/KIS, CRM, meeting-platform)
as *architecture only, no implementation* — real integration work with no
real deployment to validate against would have been speculative. The
roadmap now asks for exactly one of those to become real: "FHIR
DocumentReference oder GDT für deutsche Praxisverwaltungen. Entscheide
begründet für eine." Two genuinely different options, both plausible for
VocaDox's German outpatient-practice-shaped audience (see the
`medical_consultation`/`psychotherapy` templates and the German-only UI):

- **GDT** (Gerätedatentransfer): the long-established, near-universal
  file-based exchange format nearly every German
  Praxisverwaltungssystem (PVS) supports — simple fixed-format text
  records, decades of installed base, inherently file-drop/air-gapped by
  original design.
- **FHIR `DocumentReference`**: the modern HL7 international standard,
  a stable, well-documented base-spec JSON resource shape, the direction
  German healthcare interoperability is now moving (gematik's ISiK, the
  elektronische Patientenakte) even outside hospital settings.

## Decision

**FHIR `DocumentReference`, chosen over GDT primarily because this
codebase can verify it's correct without an internet connection or a
GDT-version-specific field table, while GDT could not be verified the
same way here.** This is a narrower, more honest reason than "FHIR is
more modern" — both would have been defensible on strategic grounds
alone. The concrete, decisive factor:

- FHIR R4's `DocumentReference` base elements (`resourceType`, `status`,
  `docStatus`, `type.coding`, `subject.display`, `content[].attachment`,
  `context.period`) are part of the stable base specification, unchanged
  across FHIR versions in ways implementation-relevant here — this
  codebase's author has high confidence in this exact shape without
  needing to fetch or verify against an external spec document (no
  network access in this working environment).
- GDT's actual field codes (Feldkennungen) are numerous and have
  meaningfully diverged across GDT 2.1/3.0 revisions. Getting one wrong
  in a real medical-documentation export is a worse failure mode than
  the alternative considered here (a file a PVS silently misreads or
  rejects, discovered only when a real practice tries to import it) —
  and this codebase's author cannot verify current field-code tables
  against an authoritative source in this environment. Implementing GDT
  "for real" here would have meant guessing at exactly the kind of
  detail this project's own established discipline (see the ADR-0031/
  ADR-0032/ADR-0033/ADR-0037 pattern of disclosing rather than guessing)
  argues against.

**Implemented as a pure local export, not a network-connected FHIR
server client — no exception to ADR-0007.** `POST
.../document/export?format=fhir` returns a downloadable FHIR resource
JSON file, exactly the same "GET with a format query param, `Response`
with a `Content-Disposition` header" pattern P0-2's DOCX/PDF export
already established (`app.documents.fhir_export.
render_fhir_document_reference` alongside `app.documents.export_formats`).
No FHIR server is contacted, no REST call is made to any external
system — a receiving PVS/KIS imports the downloaded file exactly like
GDT's own file-drop model, just in a different format.

**No real patient identity is claimed.** VocaDox never requires or
stores a real patient identifier (`ConversationParticipant.display_name`
is explicitly free-form, never required to be a real name — see that
model's own docstring). The exported resource's `subject` is
`{"display": "..."}` free text only, populated from a `PATIENT`-typed
participant if one exists, and omitted entirely otherwise — never a
resolvable `Patient` resource reference, which would claim an identity
link VocaDox was never actually given.

**Not validated against the official FHIR JSON Schema/
StructureDefinition.** No `fhir.resources`-style validation library was
added (ADR-0007-adjacent: avoid a new dependency for a single export
format). The resource is hand-built and structurally correct per the R4
base spec as understood here, but full profile conformance (e.g.
against a specific German Basisprofil/ISiK profile) is not machine-
verified — a disclosed limitation, not silently glossed over.

## Consequences

- No new dependency (backend or frontend), no new network call, no new
  secret/account — consistent with every other measure in this roadmap.
- `docs/architecture/future-considerations.md`'s Phase 10 note ("FHIR/
  HL7/PVS/KIS/CRM/Meeting-Platform adapters — architecture only, no
  implementation") is now partially superseded for FHIR `DocumentReference`
  specifically; the webhook-receiver-based extension point it describes
  remains the intended path for anything beyond this one resource type
  (Composition, other resource types, an actual FHIR REST push).
- GDT support remains a real, deferred option — not rejected on
  technical merit, only on this-environment verifiability grounds. A
  future implementation with access to a current, authoritative GDT
  field-code reference (or a real PVS vendor's integration
  documentation to validate against) would be well-positioned to add it
  as a second export format alongside this one, not a replacement for
  it.
- If a German practice-management system in the field turns out to need
  a specific FHIR profile (a Basisprofil, ISiK-specific extensions) this
  resource doesn't yet satisfy, that is real, concrete feedback this
  export can be extended to address — informed by an actual deployment,
  the same "don't build the unverified thing speculatively" discipline
  that shaped the original Phase 10 decision to defer all four adapters
  in the first place.
