# Cross-conversation search (post-GA)

## What this is

The **Gespräche** (Conversations) list has two separate search fields:

- **"Nach Titel suchen…"** — the original, narrow filter: matches only the
  conversation title.
- **"Inhalte durchsuchen…"** — full-text search across everything VocaDox
  has actually derived from a conversation: transcript segments, extracted
  facts, and the current Document. This is what you want when you
  remember something was *said* or *decided*, but not which conversation.

## Using it

Type into "Inhalte durchsuchen" and results appear below it as you type —
each result shows which conversation it's from, which kind of content
matched (Transkript / Fakten / Dokumentation), and a short snippet with
the matching words highlighted. Click a result to jump straight to that
conversation, already on the right tab; a transcript match also scrolls
to and briefly highlights the exact segment.

Results only ever include conversations you're already allowed to open —
search never reveals that a conversation exists if you couldn't see it
in the list yourself.

## What's indexed, and when

- A transcript segment is indexed as soon as alignment finishes, and
  re-indexed every time you correct its text.
- A fact is indexed when extraction creates it. If a conversation is
  re-processed, the previous run's facts (and their search entries)
  are superseded — search always reflects the current extraction, never a
  mix of old and new.
- The Document is indexed with its current content every time you compose
  it. Composing again replaces the indexed content — you'll never find an
  outdated document revision through search that no longer matches what
  the Dokumentation tab shows.

## What it can't do (yet)

This is keyword/phrase search (German-language-aware), not "ask a
question and get an answer" — that's a separate, planned capability that
builds on this index and adds a strict citation requirement of its own.
