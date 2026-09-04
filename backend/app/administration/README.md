# `app/administration/`

**Status: implemented (Phase 7).**

Houses the Phase 7 Admin Portal's backend surface that doesn't belong to
a more specific existing domain package: Dashboard aggregation, provider
status (speech/diarization/LLM — the speech/diarization endpoints predate
this phase, from Phase 3), Jobs/Workers read-model, Storage usage, and
Retention Policy CRUD. See `app.administration.router`/`.service`/
`.schemas` and `docs/admin/admin-portal.md` for the full reference.

Deliberately does NOT own: Users/Groups/Roles (`app.identity`),
Organizations (`app.organizations`), Audit (`app.audit`), Templates/
Prompts (`app.templates`), Model/Processing Profiles (`app.profiles`) —
each of those already had its own domain package with the right models/
service functions; this phase added admin-facing endpoints to those
existing packages rather than duplicating them here.

`RetentionPolicy` itself is still modeled in `app.conversations.models`
(unchanged since Phase 2) — this package only adds the CRUD/read layer
over it, per the target domain model's original placement (`docs
/architecture/domain-model.md` lists retention_policies under
"administration / compliance").
