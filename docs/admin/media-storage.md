# Admin: media storage configuration

All settings below follow the existing `Settings`
(`backend/app/platform/config.py`) / `VOCADOX_*` environment-variable
pattern — there is no settings UI yet (that's a Phase 7 admin-portal
feature); configure via `deploy/.env` and restart the backend.

| Setting | Env var | Default | Meaning |
|---|---|---|---|
| `media_storage_root` | `VOCADOX_MEDIA_STORAGE_ROOT` | `./data/media` | Filesystem root for all permanently stored media. Must be a path the backend container can write to, ideally on encrypted-at-rest storage (see "Data at rest" below). |
| `upload_temp_dir` | `VOCADOX_UPLOAD_TEMP_DIR` | `./data/tmp-uploads` | Controlled temp directory for in-flight uploads before they're validated/hashed/moved. |
| `max_upload_size_bytes` | `VOCADOX_MAX_UPLOAD_SIZE_BYTES` | 2 GiB | Hard cap on any single ingested media object. |
| `allowed_audio_content_types` | `VOCADOX_ALLOWED_AUDIO_CONTENT_TYPES` | WebM/WAV/MP3/M4A variants | Advisory allow-list — actual acceptance is decided by magic-byte sniffing (`app/media/validation.py`), not this list alone. |
| `upload_timeout_seconds` | `VOCADOX_UPLOAD_TIMEOUT_SECONDS` | 600 | Server-side timeout for a single upload/finalize request. |
| `max_active_upload_sessions_per_user` | `VOCADOX_MAX_ACTIVE_UPLOAD_SESSIONS_PER_USER` | 5 | Cap on concurrent in-progress recording-upload sessions per user (scaffolding for the `RecordingUpload` table — see ADR-0012; not yet enforced by a route in Phase 2). |

## Capacity planning

There is no per-organization or per-user storage quota in Phase 2 — total
disk usage is bounded only by `max_upload_size_bytes` per object and
however many conversations get created. Monitor `media_storage_root`'s
filesystem directly (`du -sh data/organizations/<org-id>` per
organization, thanks to the namespaced storage layout — see
[ADR-0013](../architecture/adr/0013-media-storage-layout.md)). See
`docs/operations/storage-capacity.md` for sizing guidance.

## Data at rest

VocaDox does not implement encryption-at-rest for media files itself in
Phase 2. Operators should place `media_storage_root` (and the Postgres
data volume) on infrastructure that provides encryption at rest — an
encrypted filesystem/volume, LUKS, cloud-provider-managed encrypted disks,
etc. Application-level media encryption is a possible future addition, not
implemented here; do not roll custom crypto to fill this gap.
