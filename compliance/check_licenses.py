#!/usr/bin/env python3
"""
compliance/check_licenses.py

Loads compliance/license-policy.yml, compliance/dependency-inventory.yml
(direct deps), compliance/dependency-inventory-transitive.yml (full
resolved dependency tree — see generate_transitive_inventory.py),
compliance/container-inventory.yml and compliance/model-inventory.yml,
computes approved/review_required/blocked/unknown counts across all four,
prints a summary, and exits non-zero if anything is blocked or unknown in
ANY of them — a blocked/unknown license three levels deep in the
transitive tree fails the build exactly like a direct one does.

Run from repo root as:

    python compliance/check_licenses.py

The transitive inventory must be regenerated first if it's stale relative
to the lockfiles — see generate_transitive_inventory.py's docstring for the
exact commands (also run as a CI step; see .github/workflows/ci.yml).

Dev-only dependency: PyYAML (``pip install pyyaml``). Not part of the
runtime application dependency set.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "error: PyYAML is required to run this script.\n"
        "        Install it with: pip install pyyaml\n"
    )
    sys.exit(2)

COMPLIANCE_DIR = Path(__file__).resolve().parent
POLICY_FILE = COMPLIANCE_DIR / "license-policy.yml"
DEPENDENCY_FILE = COMPLIANCE_DIR / "dependency-inventory.yml"
TRANSITIVE_FILE = COMPLIANCE_DIR / "dependency-inventory-transitive.yml"
CONTAINER_FILE = COMPLIANCE_DIR / "container-inventory.yml"
MODEL_FILE = COMPLIANCE_DIR / "model-inventory.yml"

STATUSES = ("approved", "review_required", "blocked", "unknown")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        sys.stderr.write(f"error: required file not found: {path}\n")
        sys.exit(2)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def classify_license(license_id: str, policy: dict[str, Any]) -> str:
    """Fallback classifier: derive a status from a raw license string against
    the policy buckets, used only if an inventory entry omits approval_status."""
    if license_id in (policy.get("approved") or []):
        return "approved"
    if license_id in (policy.get("review_required") or []):
        return "review_required"
    if license_id in (policy.get("blocked") or []):
        return "blocked"
    return "unknown"


def resolve_status(entry: dict[str, Any], policy: dict[str, Any]) -> str:
    status = (entry.get("approval_status") or "").strip().lower()
    if status in STATUSES:
        return status
    # Entry didn't declare a valid status explicitly recompute from license.
    return classify_license(entry.get("license", "UNKNOWN"), policy)


def print_table(title: str, rows: list[tuple[str, str, str]]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    if not rows:
        print("  (none)")
        return
    name_w = max(len(r[0]) for r in rows) + 2
    lic_w = max(len(r[1]) for r in rows) + 2
    for name, lic, status in rows:
        print(f"  {name:<{name_w}}{lic:<{lic_w}}{status}")


def main() -> int:
    policy = load_yaml(POLICY_FILE)
    dep_data = load_yaml(DEPENDENCY_FILE)
    transitive_data = load_yaml(TRANSITIVE_FILE)
    container_data = load_yaml(CONTAINER_FILE)
    model_data = load_yaml(MODEL_FILE)

    dependencies = dep_data.get("dependencies") or []
    transitive_deps = transitive_data.get("dependencies") or []
    containers = container_data.get("containers") or []
    models = model_data.get("models") or []

    # Four independent categories, each counted separately (never summed
    # into one blended "total") — dependency-inventory-transitive.yml is a
    # superset of dependency-inventory.yml (it includes direct packages
    # too, flagged direct: true), so adding both would double-count.
    category_counts: dict[str, dict[str, int]] = {
        "direct": {s: 0 for s in STATUSES},
        "transitive": {s: 0 for s in STATUSES},
        "containers": {s: 0 for s in STATUSES},
        "models": {s: 0 for s in STATUSES},
    }
    dep_rows: list[tuple[str, str, str]] = []
    container_rows: list[tuple[str, str, str]] = []
    model_rows: list[tuple[str, str, str]] = []
    offenders: list[str] = []

    for dep in dependencies:
        name = dep.get("name", "<unnamed>")
        lic = dep.get("license", "UNKNOWN")
        status = resolve_status(dep, policy)
        category_counts["direct"][status] += 1
        dep_rows.append((f"{name} ({dep.get('ecosystem', '?')})", lic, status))
        if status in ("blocked", "unknown"):
            offenders.append(f"direct:{name}")

    transitive_offenders: list[str] = []
    for dep in transitive_deps:
        name = dep.get("name", "<unnamed>")
        status = resolve_status(dep, policy)
        category_counts["transitive"][status] += 1
        if status in ("blocked", "unknown"):
            marker = f"transitive:{dep.get('ecosystem', '?')}:{name}@{dep.get('version', '?')} (scope={dep.get('scope', '?')})"
            offenders.append(marker)
            transitive_offenders.append(marker)

    for container in containers:
        name = container.get("image", "<unnamed>")
        tag = container.get("tag", "")
        lic = container.get("license", "UNKNOWN")
        status = resolve_status(container, policy)
        category_counts["containers"][status] += 1
        container_rows.append((f"{name}:{tag}", lic, status))
        if status in ("blocked", "unknown"):
            offenders.append(f"container:{name}:{tag}")
        if not container.get("pinned"):
            offenders.append(f"container:{name}:{tag} (not pinned)")

    for model in models:
        name = model.get("name", "<unnamed>")
        lic = model.get("license", "UNKNOWN")
        status = resolve_status(model, policy)
        category_counts["models"][status] += 1
        model_rows.append((name, lic, status))
        if status in ("blocked", "unknown"):
            offenders.append(f"model:{name}")

    print("=" * 60)
    print("VocaDox License Compliance Check")
    print("=" * 60)

    print_table("Direct Python / Node Dependencies", dep_rows)
    print_table("Container Images", container_rows)
    print_table("Models", model_rows)

    print(f"\nTransitive Dependencies (full resolved tree, {len(transitive_deps)} packages)")
    print("-" * 60)
    if transitive_deps:
        for status in STATUSES:
            print(f"  {status:<16}{category_counts['transitive'][status]}")
        if transitive_offenders:
            print("  offenders:")
            for o in transitive_offenders:
                print(f"    - {o}")
    else:
        print(
            "  (none found — run generate_transitive_inventory.py first; "
            "an empty transitive file is NOT the same as a clean scan)"
        )

    print("\nSummary by category (never summed together — see report for why)")
    print("-------------------------------------------------------------------")
    header = f"  {'category':<14}" + "".join(f"{s:<17}" for s in STATUSES)
    print(header)
    for category, counts in category_counts.items():
        row = f"  {category:<14}" + "".join(f"{counts[s]:<17}" for s in STATUSES)
        print(row)

    if offenders:
        print("\nBLOCKED/UNKNOWN items found:")
        for o in offenders:
            print(f"  - {o}")
        print(
            "\nresult: FAIL "
            "(blocked or unknown-licensed items present; see compliance/exceptions.yml "
            "to record an approved exception, or replace the dependency/model)"
        )
        return 1

    print("\nresult: PASS (no blocked or unknown-licensed items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
