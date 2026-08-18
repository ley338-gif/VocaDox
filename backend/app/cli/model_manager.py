"""`python -m app.cli.model_manager` — the single administrator-facing
entrypoint for installing AI model profiles, exposed as the `model-manager`
Compose service (see deploy/docker-compose.yml).

Phase 3.1 fix: the documented Phase-3 command (`docker compose run --rm
-e VOCADOX_HUGGINGFACE_TOKEN=... worker-diarization python -m
app.cli.install_models diarization-default`) never actually worked,
because `backend/worker.Dockerfile` sets
`ENTRYPOINT ["python", "-m", "app.workers.runner"]` and Compose's
`command:` override only replaces the *argument list appended after the
entrypoint* — so the real invocation was
`python -m app.workers.runner python -m app.cli.install_models
diarization-default`, which `runner.py`'s argparser correctly rejected
with "the following arguments are required: --role". Administrators
should never need to know Docker ENTRYPOINT semantics to install a model.

This module is the `model-manager` service's own `entrypoint:` (see
deploy/docker-compose.yml), so `docker compose run --rm model-manager
<args>` passes `<args>` straight to this parser — no entrypoint override,
no worker-runner argument collision:

    docker compose run --rm model-manager list
    docker compose run --rm model-manager install speech-default
    docker compose run --rm -e VOCADOX_HUGGINGFACE_TOKEN=<token> \\
        model-manager install diarization-default

Reuses `app.cli.install_models`' PROFILES registry and `install()`
function unchanged — this module is a thin, administrator-friendly UX
wrapper around it, not a second implementation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.cli.install_models import PROFILES, install


def _list_profiles() -> int:
    for name, profile in PROFILES.items():
        print(f"{name}: {profile.repo_id}@{profile.revision} ({profile.license_note})")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="model-manager",
        description="VocaDox AI model installation (see docs/admin/model-installation.md).",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("list", help="List available model profiles and their license status.")

    install_parser = subparsers.add_parser("install", help="Install a model profile.")
    install_parser.add_argument("profile", choices=sorted(PROFILES.keys()))
    install_parser.add_argument(
        "--token",
        default=None,
        help="Hugging Face access token (only required for gated profiles; falls back to "
        "VOCADOX_HUGGINGFACE_TOKEN).",
    )

    args = parser.parse_args(argv)

    if args.action == "list":
        return _list_profiles()

    from app.platform.config import get_settings

    settings = get_settings()
    token = args.token or settings.huggingface_token
    return install(
        PROFILES[args.profile],
        model_volume_root=Path(settings.model_volume_root),
        token=token,
    )


if __name__ == "__main__":
    raise SystemExit(main())
