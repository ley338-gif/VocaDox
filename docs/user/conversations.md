# Conversations

A **Conversation** is the container for one recorded/uploaded audio
session, its metadata, and everything you add around it (participants,
markers, notes). Find yours at **App → Conversations**
(`/app/conversations`).

## List view

Search by title, filter by status or type, and page through results. Each
row shows title, type, status, privacy indicator, and duration.
Conversations are always scoped to the organizations you belong to — you
will never see another organization's conversations here, even if you
somehow have its ID (see `docs/security/media-security.md` for why).

## Status meanings

| Status | Meaning |
|---|---|
| Created | Conversation exists, no audio yet |
| Recording | A browser recording is currently in progress |
| Uploaded | Source audio has been ingested |
| Normalizing | Internal processing step (Phase 2: effectively instant, no real transcoding happens yet) |
| Ready | Audio is available and playable |
| Failed | Something went wrong; you can retry an upload |

There is no "Transcribing"/"Diarizing"/"Approved" status yet — those ship
in later phases, once explicitly approved.

## Creating a conversation

See `docs/user/recording.md` and `docs/user/uploading-audio.md` — both
paths start from **New conversation**.

## Deleting a conversation

Deletion is permanent: it removes the conversation from view and destroys
the underlying audio file(s) — there is no undo. You will be asked to
confirm before it happens.
