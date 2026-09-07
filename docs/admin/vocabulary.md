# Custom transcription vocabulary (post-GA P0-3)

## What this is

Speech-to-text models can mishear domain-specific terms (drug names,
product names, jargon) that sound similar to common words. `faster-
whisper` (VocaDox's speech provider) accepts two hints that bias
decoding without retraining anything:

- **Hotwords** — a list of individual terms to recognize more reliably.
- **Initial prompt** — a short example sentence that biases spelling/
  style more broadly (e.g. medical vs. casual register).

Admin Portal → AI → **Fachwortschatz** lets you configure both, per
organization.

## Scope: organization-wide or per template

Each entry applies either:

- **Organization-wide** (no template selected) — used for every
  conversation in that organization unless a more specific entry exists.
- **To one specific Template** (e.g. "Meeting") — used only for
  conversations whose *effective* Template (the same resolution
  `app.profiles.resolver.resolve_effective_config` already uses for
  every other per-conversation setting) is that one.

At most one entry per (organization, template) pair, and at most one
organization-wide entry — creating a second one for the same scope is
rejected (409).

## What happens if nothing is configured

Nothing changes — transcription runs exactly as it did before this
feature existed. Vocabulary is entirely optional per organization.

## Measuring the effect (Evaluation Lab)

Admin Portal → Operations → **Evaluation Lab** → **Fachwortschatz** tab.
Pick a conversation that already has a *ready, reviewed* transcript (the
human-corrected text becomes the ground truth) and belongs to an
organization/template with a vocabulary entry configured. The comparison
re-runs the real speech provider on the conversation's own audio twice —
once without any vocabulary, once with — and reports the Word Error Rate
of each against the ground truth. Lower is better.

This requires a real, installed speech model (not the `fake` provider
used in CI) to produce a meaningful result — see
`docs/admin/speech-provider.md`.
