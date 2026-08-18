# Fresh install (Phase 3.1)

A real product workflow, from a fresh checkout to a working
conversation-processing stack, without reading source code or discovering
undocumented Docker behavior. This page exists because a real fresh/local
install previously let the stack start against a database with **no
Alembic revision at all** — `bootstrap_admin` then failed with
`asyncpg.exceptions.UndefinedTableError: relation "permissions" does not
exist` — and separately, the documented model-install command never
actually worked (see `docs/admin/model-installation.md`'s note). Both are
fixed; this page is the exact, verified sequence.

## The deterministic lifecycle

```
Postgres (healthy) -> migrate (alembic upgrade head, one-shot) -> backend/workers (start) -> bootstrap_admin (you run this) -> [optional] model install -> conversation processing works
```

Every step after "Postgres healthy" is enforced by `depends_on:
condition: service_completed_successfully` in
`deploy/docker-compose.yml` — `backend`/`worker-speech`/
`worker-diarization` cannot start until `migrate` has exited 0. You do
not need to remember to run migrations yourself; you do still need to run
`bootstrap_admin` yourself (creating the first admin is a deliberate,
explicit administrator action, never automatic — see
`docs/admin/README.md`).

## Step by step

1. **Configure environment.**
   ```sh
   cp deploy/.env.example .env
   ```
   Edit `.env` if you need non-default ports/credentials. If you plan to
   install the diarization model, also set `VOCADOX_HUGGINGFACE_TOKEN`
   here (never commit this file with a real token in it — `.env` is
   gitignored).

2. **Start the stack.**
   ```sh
   docker compose up -d
   ```
   This builds (if needed) and starts Postgres, Valkey, runs `migrate`
   to completion, then starts `backend`, `worker-speech`,
   `worker-diarization`, and `frontend`. Confirm:
   ```sh
   docker compose ps          # migrate should show "Exited (0)"
   curl http://localhost:8000/health/ready
   ```

3. **Create the first administrator.**
   ```sh
   docker compose exec backend python -m app.identity.bootstrap_admin \
     --username admin --display-name "Administrator" --email admin@example.org
   ```
   Prompts for a password interactively (recommended). See
   `docs/admin/README.md` for the full flag reference and the
   `--force`/disaster-recovery case.

4. **(Optional) Install real speech/diarization models.** Without this
   step, `worker-speech`/`worker-diarization` use deterministic `fake`
   providers — real conversation processing still works end-to-end
   (useful for evaluating the product without any model download), just
   without real transcription/diarization output.
   ```sh
   docker compose run --rm model-manager install speech-default
   docker compose run --rm -e VOCADOX_HUGGINGFACE_TOKEN=<your-hf-token> \
     model-manager install diarization-default
   ```
   Then set `VOCADOX_SPEECH_PROVIDER=faster_whisper` /
   `VOCADOX_DIARIZATION_PROVIDER=pyannote` (in `.env` or the shell
   environment) and restart the two worker services:
   ```sh
   docker compose up -d --force-recreate worker-speech worker-diarization
   ```
   Full detail, including the real Hugging Face account/token
   prerequisites and exactly what gets downloaded:
   `docs/admin/model-installation.md`, `docs/admin/diarization-provider.md`.

5. **Verify conversation processing.** Log in as the admin created in
   step 3, create an organization and a conversation (via the frontend at
   `http://localhost:5173`, or the API directly), upload an audio file,
   and trigger `POST /conversations/{id}/process/transcript`. Watch
   `docker compose logs -f worker-speech worker-diarization` for
   progress; a `ready` transcript with speaker-attributed segments
   confirms the full NORMALIZE -> TRANSCRIBE -> DIARIZE -> ALIGN pipeline
   works.

## What gets destroyed by `docker compose down -v`

`-v` deletes every named volume: `vocadox_postgres_data` (all database
state — organizations, users, conversations, transcripts, everything),
`vocadox_valkey_data` (queue/session state), `vocadox_backend_data`
(uploaded/normalized conversation media), and **`vocadox_models_data`**
(every installed AI model — a full re-download, including re-accepting
gated Hugging Face terms if your token session lapsed, is required after
this). Plain `docker compose down` (no `-v`) or `docker compose stop`
preserve all of this.

## Upgrading an existing installation

Pull the new code, then:
```sh
docker compose up -d --build
```
`migrate` re-runs `alembic upgrade head` automatically (a no-op if
already current, otherwise applies exactly the new revisions) before
`backend`/the workers restart. No manual migration step, no data loss —
verified in `PHASE_3_1_VALIDATION_REPORT.md`'s migration-lifecycle
section against a real Phase-3-schema database with existing job rows.

## Troubleshooting

See `docs/operations/processing-troubleshooting.md` for processing-
pipeline-specific issues. If `bootstrap_admin` still reports
`UndefinedTableError`, check `docker compose ps` — if `migrate` shows
anything other than `Exited (0)`, check `docker compose logs migrate`
before re-running bootstrap; do not work around it by running
`alembic upgrade head` manually inside a different container, which
usually indicates the `migrate` service itself failed for a real reason
(e.g. Postgres credentials mismatch) that re-running bootstrap will not
fix.
