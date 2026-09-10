# 0046 — Progressive disclosure for workspace complexity

## Status

Accepted (2026-09-10), Phase 14 UX complexity review.

## Context

VocaDox has grown from a recording workflow into a broad evidence, review,
document, search, task and administration product. Phase 14 asks whether normal
users still see the intended path:

`Gespräch → Aufnahme → Transkript → Protokoll/Dokument → Prüfung → Freigabe`

This review inventories the shipped navigation and conversation view. It does
not introduce a new information architecture or hide capabilities without
usage evidence.

## Findings

### Global navigation

The workspace and administration boundary is already strong:

- normal workspace navigation contains Dashboard, Gespräche, Aufgaben and the
  permission-gated Ask VocaDox;
- Administration is a distinct route tree and appears only with the matching
  permission;
- provider, model, prompt, worker, storage, retention, integration, security and
  audit controls are already confined to grouped administration sections;
- backend route permissions remain the security boundary; navigation visibility
  is only presentation.

No global navigation restructure is justified in Phase 14.

### Conversation view

The conversation detail exposes nine primary tabs: Übersicht, Transkript,
Fakten, Protokoll, Dokumentation, Prüfung, Aufgaben, Recap and Audio. Four more
supporting views — Verlauf, Verwandt, Notizen and Aktivität — are reached from
the overview. The primary row is the main cognitive-load hotspot.

The tabs fall into three user intents:

| Intent | Current views |
| --- | --- |
| Core production flow | Audio, Transkript, Protokoll, Dokumentation, Prüfung |
| Evidence and follow-up | Fakten, Aufgaben |
| Sharing and supporting context | Recap, Verlauf, Verwandt, Notizen, Aktivität |

This is a presentation issue, not an authorization issue. Removing tabs now
would risk breaking saved habits and deep links, and usage evidence is not
available to rank secondary views honestly.

### Terminology

The mixed English/German label `Review` obscures the core workflow step for
German-speaking users. Administration also mixed `AI` and `Integrations` into
otherwise German section titles. These labels can be corrected without changing
routes, permissions, data or behavior.

## Decision

1. Keep the current route and permission structure.
2. Rename `Review` to `Prüfung`, `AI` to `KI`, and `Integrations` to
   `Integrationen`. Internal route and tab IDs remain unchanged.
3. Treat the existing Übersicht as the workflow-oriented entry point. Its next
   actions should continue leading users into the appropriate core step.
4. Defer collapsing or regrouping conversation tabs until moderated usability
   sessions or privacy-preserving, explicitly approved product research provides
   evidence. No telemetry is added.
5. If evidence confirms the hotspot, implement progressive disclosure in a
   separate change: keep Übersicht, Audio, Transkript, Protokoll, Dokumentation
   and Prüfung immediately visible; place Fakten, Aufgaben, Recap and contextual
   views behind an accessible `Mehr` control. Preserve programmatic/deep-link tab
   selection and permission behavior.

## Validation criteria for a later navigation change

- A new user can start/finish a recording and reach the final approved document
  without opening an expert view.
- Fact-to-evidence-to-transcript navigation remains one direct interaction.
- Keyboard and narrow-screen access expose every moved view.
- Links from search, tasks and Ask VocaDox still open the intended tab and source.
- No feature visibility is used as a substitute for backend authorization.
- The Playwright evidence-chain and permission-boundary golden paths remain green.

## Consequences

- Phase 14 makes terminology consistent without a disruptive redesign.
- The principal complexity hotspot and a concrete target structure are recorded
  for evidence-led follow-up.
- Product analytics are not introduced, preserving the on-premise/no-telemetry
  posture. Usability evidence must therefore come from explicitly organized
  research or support feedback.
