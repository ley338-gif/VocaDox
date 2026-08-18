"""`python -m app.cli.install_models <profile>` — the explicit,
admin-initiated model install step (spec: "Model installation" /
"no silent internet access from workers in production").

Usage:
    python -m app.cli.install_models speech-default
    python -m app.cli.install_models diarization-default   # requires
        VOCADOX_HUGGINGFACE_TOKEN (or --token) — the pipeline is MIT-
        licensed but gated on Hugging Face (see
        docs/architecture/adr/0017-diarization-provider-selection.md).
    python -m app.cli.install_models --list

Downloads a pinned revision from Hugging Face into
`Settings.model_volume_root/<profile>`, verifies the download actually
landed (non-empty directory with the expected marker file), and never
re-downloads if the target directory already exists and looks valid
(idempotent — matches "don't re-download every restart"). Never called
by any API route or by the worker's normal request path — network access
happens only when an admin explicitly runs this.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

PROFILES: dict[str, ModelProfile] = {}


@dataclass(frozen=True)
class ModelProfile:
    name: str
    repo_id: str
    revision: str
    marker_file: str
    requires_token: bool
    license_note: str


def _register(profile: ModelProfile) -> None:
    PROFILES[profile.name] = profile


_register(
    ModelProfile(
        name="speech-default",
        repo_id="Systran/faster-whisper-small",
        revision="536b0662742c02347bc0e980a01041f333bce12",
        marker_file="model.bin",
        requires_token=False,
        license_note="MIT (verified: https://huggingface.co/Systran/faster-whisper-small)",
    )
)
_register(
    ModelProfile(
        name="diarization-default",
        repo_id="pyannote/speaker-diarization-3.1",
        revision="84fd25912480287da0247647c3d2b4853cb3ee5",
        marker_file="config.yaml",
        requires_token=True,
        license_note=(
            "MIT (verified: https://huggingface.co/pyannote/speaker-diarization-3.1) — "
            "gated download, requires accepting the model's terms on Hugging Face and a "
            "user access token (never bundled/redistributed by VocaDox itself)."
        ),
    )
)


def _is_installed(target_dir: Path, marker_file: str) -> bool:
    return target_dir.exists() and (target_dir / marker_file).exists()


def install(profile: ModelProfile, *, model_volume_root: Path, token: str | None) -> int:
    target_dir = model_volume_root / profile.name

    if _is_installed(target_dir, profile.marker_file):
        print(f"[{profile.name}] already installed at {target_dir} — skipping re-download.")
        return 0

    if profile.requires_token and not token:
        print(
            f"[{profile.name}] ERROR: this model is gated and requires a Hugging Face "
            "access token. Accept the model's terms at "
            f"https://huggingface.co/{profile.repo_id} while logged in, then re-run with "
            "--token <hf_token> or VOCADOX_HUGGINGFACE_TOKEN set.",
            file=sys.stderr,
        )
        return 1

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print(
            "ERROR: huggingface_hub is not installed in this environment "
            "(install the backend's [ai] extra: pip install -e 'backend/[ai]').",
            file=sys.stderr,
        )
        return 1

    print(f"[{profile.name}] downloading {profile.repo_id}@{profile.revision} -> {target_dir}")
    print(f"[{profile.name}] license: {profile.license_note}")
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=profile.repo_id,
        revision=profile.revision,
        local_dir=str(target_dir),
        token=token,
    )

    if not _is_installed(target_dir, profile.marker_file):
        print(
            f"[{profile.name}] ERROR: download completed but expected marker file "
            f"{profile.marker_file} is missing — install did not land correctly.",
            file=sys.stderr,
        )
        return 1

    print(f"[{profile.name}] installed successfully at {target_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install a VocaDox AI model profile.")
    parser.add_argument("profile", nargs="?", choices=sorted(PROFILES.keys()))
    parser.add_argument("--token", default=None, help="Hugging Face access token")
    parser.add_argument("--list", action="store_true", help="List available profiles and exit")
    args = parser.parse_args(argv)

    if args.list or not args.profile:
        for name, profile in PROFILES.items():
            print(f"{name}: {profile.repo_id}@{profile.revision} ({profile.license_note})")
        return 0

    from app.platform.config import get_settings

    settings = get_settings()
    token = args.token or settings.huggingface_token
    return install(
        PROFILES[args.profile], model_volume_root=Path(settings.model_volume_root), token=token
    )


if __name__ == "__main__":
    raise SystemExit(main())
