# gdt-bridge (prototype)

A standalone GDT (Gerätedatentransfer) connector for VocaDox — **not**
part of the VocaDox backend, never a dependency of it, and never
depended on by it. Runs on or near a German medical practice's PC:

1. Watches a local folder for an inbound `.gdt` file containing patient
   data, creates a VocaDox conversation (+ a `patient` participant, if
   a name was found) via VocaDox's Integration API.
2. Polls VocaDox until that conversation's document is approved.
3. Downloads the export (a PDF+GDT bundle, or a text-only GDT file) and
   writes it to a local export folder for the practice's PVS to import,
   rewriting the GDT file's file-path field to the real local path.

See `docs/architecture/adr/0041-gdt-export-and-connector-prototype.md`
in the main VocaDox repo for the full design rationale and — important
— the disclosed list of what is **not** verified here (GDT field-code
confidence, the unresolved request-side Satzart number, character-set
handling, and more). **This is a prototype, not a certified integration
with any real PVS product.** Validate against your actual target PVS
before any real-practice use.

## Configuration

Environment variables (prefix `GDT_BRIDGE_`) or a TOML file passed via
`--config`:

| Setting | Env var | Default |
|---|---|---|
| VocaDox base URL | `GDT_BRIDGE_BASE_URL` | *(required)* |
| Service Account API key | `GDT_BRIDGE_API_KEY` | *(required)* |
| Import folder | `GDT_BRIDGE_IMPORT_DIR` | `./gdt_import` |
| Processed folder | `GDT_BRIDGE_PROCESSED_DIR` | `./gdt_processed` |
| Failed folder | `GDT_BRIDGE_FAILED_DIR` | `./gdt_failed` |
| Export folder | `GDT_BRIDGE_EXPORT_DIR` | `./gdt_export` |
| Export format | `GDT_BRIDGE_EXPORT_FORMAT` | `gdt-pdf` (or `gdt-text`) |
| Poll interval (seconds) | `GDT_BRIDGE_POLL_INTERVAL_SECONDS` | `15` |

The Service Account needs, at minimum, the `conversation:create` and
`conversation:manage-participants` scopes (inbound half) plus
`document:read` (outbound half) — create it under **Admin → Integrations
→ Service Accounts** in VocaDox, scoped to the practice's organization.

## Running

```bash
pip install -e .
python -m gdt_bridge.cli validate-config --config gdt_bridge.toml
python -m gdt_bridge.cli test-connection --config gdt_bridge.toml
python -m gdt_bridge.cli run --config gdt_bridge.toml
```

Or via Docker: `docker build -t gdt-bridge . && docker run --env-file .env -v ./gdt_import:/app/gdt_import -v ./gdt_export:/app/gdt_export gdt-bridge`.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

No live VocaDox instance is required — the codec and inbound-parsing
tests exercise pure functions only.
