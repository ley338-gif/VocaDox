"""Static architecture-boundary checks (Phase 0 remediation, item 6).

We deliberately did NOT add `import-linter` (or any similar dependency)
for this — every domain package under `app/` is still an empty,
documented placeholder (see each package's README.md), so a real
dependency-graph linter has nothing meaningful to enforce yet and would be
pure overhead. Instead: three small, targeted static checks over the
source tree, using only the stdlib `ast` module, that will start actually
catching violations the moment domain code lands in Phase 1+.

Checked invariants (see ADR-0001, ADR-0002, ADR-0005):

1. No domain package imports the `valkey` client directly — only
   `app.platform.valkey` may do that (ADR-0002: "no domain code may depend
   on Valkey directly").
2. No domain package imports a concrete provider implementation
   (`Fake*Provider`, `LocalFilesystemStorage`) — domain code should depend
   on the abstract interface (`SpeechToTextProvider`, `StorageProvider`,
   ...) and receive a concrete instance via dependency injection, never
   import/instantiate one itself. This is what "provider interfaces stay
   separated from implementations" means in practice here: a *usage*
   boundary, not a requirement that interface and implementation classes
   live in different files (they're colocated in app/providers/*.py today,
   which is fine at this scale — see PHASE_0_VALIDATION_REPORT.md).
3. No class anywhere in the codebase is named `RedisService` (or similar),
   per ADR-0002's explicit naming rule.

These are regular pytest tests — they run in CI alongside everything else
and fail loudly (with the offending file/line) the moment a future PR
violates the boundary, rather than relying on code review to catch it.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

# Domain packages (spec §7) — everything under app/ except the two
# cross-cutting packages, core/, and top-level files (main.py, __init__.py).
_NON_DOMAIN_DIRS = {"platform", "providers", "core"}


def _domain_python_files() -> list[Path]:
    files = []
    for child in APP_ROOT.iterdir():
        if not child.is_dir() or child.name in _NON_DOMAIN_DIRS or child.name.startswith("__"):
            continue
        files.extend(child.rglob("*.py"))
    return files


def _all_python_files() -> list[Path]:
    return list(APP_ROOT.rglob("*.py"))


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            for alias in node.names:
                names.add(alias.name)
    return names


def test_domain_packages_do_not_import_valkey_client_directly() -> None:
    offenders = []
    for path in _domain_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = _imported_names(tree)
        if "valkey" in names:
            offenders.append(str(path))
    assert not offenders, (
        "Domain packages must not import the `valkey` client directly — "
        f"depend on app.platform.valkey's Protocol interfaces instead. Offenders: {offenders}"
    )


def test_domain_packages_do_not_import_concrete_provider_implementations() -> None:
    concrete_impl_names = {
        "FakeSpeechProvider",
        "FakeDiarizationProvider",
        "FakeLLMProvider",
        "LocalFilesystemStorage",
    }
    offenders = []
    for path in _domain_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = _imported_names(tree)
        hit = names & concrete_impl_names
        if hit:
            offenders.append((str(path), sorted(hit)))
    assert not offenders, (
        "Domain packages must depend on provider *interfaces* "
        "(SpeechToTextProvider, DiarizationProvider, LLMProvider, StorageProvider), "
        f"never a concrete implementation directly. Offenders: {offenders}"
    )


def test_no_class_named_redis_service_anywhere() -> None:
    offenders = []
    for path in _all_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "redis" in node.name.lower():
                offenders.append(f"{path}:{node.lineno} class {node.name}")
    assert not offenders, (
        f"No class may be named to imply a hard Redis dependency (ADR-0002). Offenders: {offenders}"
    )
