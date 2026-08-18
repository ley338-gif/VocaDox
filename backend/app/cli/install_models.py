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
class DependentRepo:
    """A model repo the profile's PRIMARY pipeline references by name and
    resolves internally at pipeline-construction time (e.g. pyannote's
    `config.yaml` names `segmentation: pyannote/segmentation-3.0` — a
    second, separate Hugging Face repo, not bundled inside
    speaker-diarization-3.1's own snapshot).

    Found by real testing, not by reading pyannote's docs: installing only
    `pyannote/speaker-diarization-3.1` and then running real diarization
    inference against it failed with a live `HEAD
    https://huggingface.co/pyannote/segmentation-3.0/... 401 Unauthorized`
    network call from inside the worker container — i.e. the "one model,
    one download" assumption baked into Phase 3's `install_models.py` was
    simply wrong. `pyannote/speaker-diarization-3.1` actually needs THREE
    Hugging Face repos to run fully offline: itself, its segmentation
    sub-model, and its speaker-embedding sub-model. All three are
    downloaded together by installing the `diarization-default` profile,
    into a shared, offline-forced Hugging Face cache directory (not each
    profile's own `local_dir`) — see PyannoteConfig.cache_dir and
    PyannoteDiarizationProvider._ensure_loaded's `HF_HUB_OFFLINE=1`.
    """

    repo_id: str
    revision: str
    license_note: str
    # Restricts the download to matching files only (huggingface_hub
    # `allow_patterns` glob syntax) — used for
    # pyannote/speaker-diarization-community-1 below, where VocaDox only
    # needs its `plda/` subfolder, not that pipeline's own (much larger,
    # unused) segmentation/embedding weights.
    allow_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelProfile:
    name: str
    repo_id: str
    revision: str
    marker_file: str
    requires_token: bool
    license_note: str
    dependent_repos: tuple[DependentRepo, ...] = ()


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
        dependent_repos=(
            # config.yaml's `segmentation:` component. Also gated (MIT) —
            # requires accepting its own separate terms at
            # https://hf.co/pyannote/segmentation-3.0, even for a token that
            # already has speaker-diarization-3.1 access.
            DependentRepo(
                repo_id="pyannote/segmentation-3.0",
                revision="e66f3d3b9eb0873085418a7b813d3b369bf160bb",
                license_note=(
                    "MIT (verified: https://huggingface.co/pyannote/segmentation-3.0) — "
                    "gated, requires its own separate terms acceptance."
                ),
            ),
            # config.yaml's `embedding:` component. NOT gated.
            DependentRepo(
                repo_id="pyannote/wespeaker-voxceleb-resnet34-LM",
                revision="837717ddb9ff5507820346191109dc79c958d614",
                license_note=(
                    "CC-BY-4.0 (verified: "
                    "https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM) — "
                    "trained on VoxCeleb, which the model card states carries the "
                    "dataset's own CC-BY-4.0 license; not gated."
                ),
            ),
            # NOT named anywhere in config.yaml — a pyannote.audio 4.x
            # library quirk found by real diarization inference testing,
            # not by reading any pyannote documentation:
            # `SpeakerDiarization.__init__` unconditionally loads a PLDA
            # transform at construction time regardless of which
            # `clustering:` algorithm config.yaml actually selects — even
            # though the PLDA object is only ever *used* downstream by
            # `VBxClustering`, never by `AgglomerativeClustering` (what
            # speaker-diarization-3.1's own config.yaml sets). Its default
            # value points at `pyannote/speaker-diarization-community-1`
            # (a newer, different, gated pipeline VocaDox does not use and
            # was not selected in ADR-0017) — so without this download, a
            # fully-installed, correctly-configured speaker-diarization-3.1
            # pipeline still fails at load time on a repo it doesn't
            # actually need for AgglomerativeClustering. Restricted to only
            # the `plda/` subfolder (a few MB) — the rest of that pipeline
            # (its own segmentation/embedding weights) is never touched.
            DependentRepo(
                repo_id="pyannote/speaker-diarization-community-1",
                revision="3533c8cf8e369892e6b79ff1bf80f7b0286a54ee",
                license_note=(
                    "CC-BY-4.0 (verified: "
                    "https://huggingface.co/pyannote/speaker-diarization-community-1) — "
                    "gated; only its plda/ subfolder is downloaded, never its own "
                    "segmentation/embedding pipeline weights, which VocaDox does not use."
                ),
                allow_patterns=("plda/*",),
            ),
        ),
    )
)


def hf_cache_dir(model_volume_root: Path) -> Path:
    """Shared Hugging Face cache for every profile's dependent repos —
    deliberately separate from each profile's own `local_dir` snapshot
    (which uses the flat, non-cache `local_dir=` layout `snapshot_download`
    produces) since dependent repos are resolved by pyannote.audio's own
    internal `Model.from_pretrained` calls, which expect the normal
    huggingface_hub cache layout, not a flat directory. Lives under the
    same persistent model volume so it survives container recreation
    exactly like every other installed model (`docker compose down -v`
    removes it, same as everything else here)."""
    return model_volume_root / "hf-cache"


def _is_installed(target_dir: Path, marker_file: str) -> bool:
    return target_dir.exists() and (target_dir / marker_file).exists()


def install(profile: ModelProfile, *, model_volume_root: Path, token: str | None) -> int:
    target_dir = model_volume_root / profile.name
    already_installed = _is_installed(target_dir, profile.marker_file)

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

    if already_installed:
        print(f"[{profile.name}] already installed at {target_dir} — skipping re-download.")
    else:
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

    # Dependent repos: the primary pipeline resolves these BY NAME at
    # pipeline-construction time (see DependentRepo's docstring) — they
    # must land in the shared HF cache (not target_dir) so
    # PyannoteDiarizationProvider's HF_HUB_OFFLINE=1 load finds them
    # without ever reaching the network.
    if profile.dependent_repos:
        from huggingface_hub.file_download import repo_folder_name

        cache_dir = hf_cache_dir(model_volume_root)
        cache_dir.mkdir(parents=True, exist_ok=True)
        for dep in profile.dependent_repos:
            print(f"[{profile.name}] fetching dependent repo {dep.repo_id}@{dep.revision}")
            print(f"[{profile.name}]   license: {dep.license_note}")
            snapshot_download(
                repo_id=dep.repo_id,
                revision=dep.revision,
                cache_dir=str(cache_dir),
                token=token,
                allow_patterns=list(dep.allow_patterns) or None,
            )
            # pyannote.audio resolves each dependent repo by its bare repo_id
            # at pipeline-load time, with NO revision pinned on its end — it
            # always effectively asks for "main". `snapshot_download` above
            # was called with an explicit commit-hash `revision=`, which
            # huggingface_hub treats as already-resolved and therefore never
            # writes a `refs/main -> commit_hash` pointer for (that pointer
            # is only written when the requested revision is a *symbolic*
            # name, not already a commit hash). Real testing found this the
            # hard way: with HF_HUB_OFFLINE=1 forced (see
            # app/workers/_offline_env.py) and this repo genuinely fully
            # downloaded at the pinned commit, pyannote's own unpinned
            # `get_model(dep.repo_id)` call still failed with
            # `LocalEntryNotFoundError` because there was no `refs/main`
            # entry for it to resolve. Writing it explicitly here — to the
            # exact commit we already verified and downloaded, no extra
            # network round-trip — closes that gap.
            ref_path = cache_dir / repo_folder_name(repo_id=dep.repo_id, repo_type="model")
            ref_path = ref_path / "refs" / "main"
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(dep.revision)
        print(
            f"[{profile.name}] {len(profile.dependent_repos)} dependent repo(s) cached at "
            f"{cache_dir}"
        )

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
