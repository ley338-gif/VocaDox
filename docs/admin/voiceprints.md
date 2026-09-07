# Voiceprint enrollment for known speakers (post-GA P1-2)

## What this is

Every diarization run already clusters a conversation's audio into
distinct speaker voices ("Detected Speakers", e.g. `SPEAKER_00`); pyannote
also computes a numeric voice embedding per cluster internally. Until now
that embedding was discarded, and matching a detected speaker to a real
person (a `Known Speaker` — Admin Portal → **Bekannte Personen**, or
directly in a conversation's "Teilnehmer" panel) was always a fully
manual, per-conversation pick from a list.

This feature stores that embedding and uses it for exactly one thing:
**suggesting** that a newly detected speaker in a *different* conversation
is probably the same known person, with a confidence score — never
assigning anything by itself.

## How it works

1. **Enroll** — open a conversation's "Sprecher verwalten" dialog. Any
   detected speaker with a computed voiceprint (`has_voiceprint`) shows a
   "Stimmprofil speichern als…" control: pick the Known Speaker this
   voice belongs to and save. Each enrollment folds the new sample into
   that person's running-average voiceprint (a new person needs only one
   enrollment; enrolling again from a later conversation refines it
   further).
2. **Suggest** — the next time diarization runs *anywhere in the same
   organization*, every new detected speaker's embedding is compared
   against every enrolled Known Speaker's voiceprint. A match at or above
   the confidence threshold (cosine similarity ≥ 0.75) is recorded as a
   suggestion — never applied.
3. **Accept or ignore** — a suggested speaker shows "Vorschlag: {Name}
   (NN% Übereinstimmung)" with an "Übernehmen" button in the same dialog.
   Clicking it creates (or reuses) a conversation participant linked to
   that Known Speaker and assigns the detected speaker to it — the exact
   same action a manual assignment would perform. Ignoring the suggestion
   has no effect at all; the detected speaker stays unassigned until a
   human acts, same as before this feature existed.

## What this deliberately does not do

- **No automatic assignment, ever.** A suggestion is a hint attached to
  the detected speaker (`suggested_known_speaker_id`/
  `suggested_confidence` in the API); it never writes `participant_id`.
  This mirrors the existing, disclosed principle for all speaker
  assignment (see `app.diarization.models.DetectedSpeaker`'s docstring)
  and the reason automatic matching was originally deferred (see
  `alembic/versions/0013_known_speakers.py`): real acoustic accuracy
  across genuinely distinct voices has not been independently verified,
  so a silent auto-match would risk misattributing what a real person
  said to the wrong name.
- **No retroactive rewrite.** Accepting a suggestion (or a manual
  enrollment) never changes any already-extracted fact or already-
  composed document — same disclosed limitation as per-segment speaker
  correction.
- **No new runtime network dependency.** Voiceprints are pyannote's own
  local embedding output; matching is a small pure-Python cosine
  similarity computation (`app.people.matching`), no additional model or
  service.

## Permissions

- Viewing/accepting suggestions uses the existing `speaker:assign`
  permission (same as any other speaker assignment).
- Enrolling a voiceprint additionally requires `known-speaker:manage`
  (it writes to an organization-wide Known Speaker, not just this
  conversation) — the same two-permission combination the "Teilnehmer
  als bekannte Person merken" action already requires.

## Data & retention

A voiceprint is a numeric vector derived from a person's voice, stored on
`known_speakers.voiceprint_embedding`. It is deleted the moment its
Known Speaker record is deleted (no separate retention policy) and is
never exported, logged, or included in any generated document — the
Evidence Chain never cites it, since it is a matching aid, not evidence.
