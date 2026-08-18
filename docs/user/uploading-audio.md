# Uploading an existing audio file

**New conversation → Upload audio**, fill in the title/type/organization,
choose a file, then **Create and upload**.

## Supported formats

WebM/Opus, WAV, MP3, M4A — nothing else. The file is checked by its actual
content (not just its extension or the browser-reported type), so
renaming an unsupported file won't make it accepted, and a corrupted or
mismatched file will be rejected with a clear error rather than silently
failing later.

## Limits

- Empty files are rejected.
- There is a maximum upload size (ask your administrator for your
  deployment's configured limit — see `docs/admin/media-storage.md`);
  large files (tested up to 120+ minutes of audio) upload without your
  browser or the server needing to hold the entire file in memory at
  once.

## What happens after upload

The file's integrity is verified with a SHA-256 hash computed at upload
time and stored permanently — the same original bytes stay on the server
unchanged for as long as the conversation exists (see
`docs/architecture/adr/0011-source-media-separation.md`). The conversation
moves to **Uploaded** status and its Audio tab becomes playable
immediately.

If the create step succeeds but the upload itself fails, you're taken to
the conversation's detail page where you can retry the upload from the
Audio tab.
