#!/usr/bin/env python3
"""
compliance/generate_transitive_inventory.py

Regenerates compliance/dependency-inventory-transitive.yml from the actual
resolved dependency trees (not hand-maintained) — the full transitive
closure of every Python and Node package actually installed, not just the
~26 direct/top-level packages tracked in dependency-inventory.yml.

This addresses a real gap: `compliance/check_licenses.py` originally only
checked direct dependencies. A blocked/unknown license three levels deep in
the tree would have gone completely unnoticed. Policy (compliance/
license-policy.yml) is UNKNOWN=BLOCKED, and that must apply to every
resolved package, not just the ones we happened to list by hand.

INPUTS (raw JSON, produced by the *actual* license-scanning tools below —
never hand-typed):

  Python, production install only (`pip install .`, no [dev] extra — this
  is exactly what ships in backend/Dockerfile's image):
      python -m venv /tmp/prod_venv && source /tmp/prod_venv/*/activate
      pip install -e backend/
      pip install pip-licenses   # MIT license — see this file's own entry
      pip-licenses --format=json --with-urls > pip_prod_licenses.json

  Python, full dev environment (adds ruff/mypy/pytest/pip-licenses/
  pip-audit and their own transitive deps — NOT shipped in the Docker
  image, but still worth knowing about since it runs in CI/dev machines):
      pip install -e "backend/[dev]"
      pip-licenses --format=json --with-urls > pip_dev_licenses.json

  Node, production dependencies only (`npm ls --production` scope — what
  ends up in the Vite build output / frontend/Dockerfile `runtime` stage):
      npx license-checker --production --json --excludePrivatePackages \
          > npm_prod_licenses.json

  Node, full tree (prod + dev — includes eslint/vite/vitest/testing-library
  and their transitive deps; NOT shipped, but scanned anyway since a
  compromised/mislicensed build-tool dependency is still a real risk):
      npx license-checker --json --excludePrivatePackages \
          > npm_all_licenses.json

Tool licenses (checked before use, per compliance policy):
  - pip-licenses (PyPI): MIT
  - pip-audit (PyPI): Apache-2.0
  - license-checker (npm): BSD-3-Clause
All three are approved and are build/dev-tooling only — never imported by
application code, never shipped in a runtime image.

USAGE:
    python compliance/generate_transitive_inventory.py \
        --pip-prod compliance/_raw_pip_prod_licenses.json \
        --pip-dev compliance/_raw_pip_licenses.json \
        --npm-prod compliance/_raw_npm_licenses_prod.json \
        --npm-all compliance/_raw_npm_licenses_all.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

COMPLIANCE_DIR = Path(__file__).resolve().parent
POLICY_FILE = COMPLIANCE_DIR / "license-policy.yml"
DIRECT_INVENTORY_FILE = COMPLIANCE_DIR / "dependency-inventory.yml"
OUTPUT_FILE = COMPLIANCE_DIR / "dependency-inventory-transitive.yml"

# Our own first-party package(s) — not a third-party dependency, excluded
# from the inventory.
FIRST_PARTY_NAMES = {"vocadox-backend", "vocadox-frontend"}

# pip-licenses sometimes only knows the OSI trove classifier ("BSD
# License"), which doesn't say 2-clause vs 3-clause — too ambiguous to
# blanket-alias. Verified individually via the PyPI JSON API / project
# LICENSE file instead of guessed; add an entry here only after doing that
# verification (see compliance/dependency-inventory-transitive.yml notes).
PACKAGE_LICENSE_OVERRIDES: dict[tuple[str, str], str] = {
    ("pypi", "colorama"): "BSD-3-Clause",  # verified via PyPI JSON + project README, 2026-08-17
    ("pypi", "httpx"): "BSD-3-Clause",  # matches the direct-dependency entry in dependency-inventory.yml, verified via PyPI JSON, 2026-08-17
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_license(raw: str) -> str:
    """pip-licenses / license-checker both sometimes append ' License' or
    use slightly different punctuation than SPDX. Normalize the handful of
    variants we've actually observed rather than guessing broadly."""
    raw = raw.strip()
    aliases = {
        "MIT License": "MIT",
        "BSD License": "BSD",  # ambiguous 2 vs 3 clause; pip-licenses can't
        # tell them apart from classifiers alone for a few packages.
        "Apache Software License": "Apache-2.0",
        "Apache 2.0": "Apache-2.0",
        "PYTHON SOFTWARE FOUNDATION LICENSE": "PSF-2.0",
        "Python Software Foundation License": "PSF-2.0",
        "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    }
    return aliases.get(raw, raw)


def split_spdx_expression(expr: str) -> tuple[str, list[str]]:
    """Return (operator, [tokens]) for simple 'A AND B' / 'A OR B'
    expressions (optionally parenthesized), else ("SINGLE", [expr])."""
    inner = expr.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1].strip()
    if " AND " in inner:
        return "AND", [t.strip() for t in inner.split(" AND ")]
    if " OR " in inner:
        return "OR", [t.strip() for t in inner.split(" OR ")]
    if "; " in inner:
        # pip-licenses joins multiple PyPI trove classifiers this way (e.g.
        # "Apache Software License; MIT License" for a dual-licensed
        # package like uvloop). Each classifier names an *alternative* the
        # licensee may pick, i.e. the same semantics as SPDX 'OR'.
        return "OR", [t.strip() for t in inner.split("; ")]
    return "SINGLE", [inner]


def classify(license_id: str, policy: dict[str, Any]) -> str:
    approved = set(policy.get("approved") or [])
    review = set(policy.get("review_required") or [])
    blocked = set(policy.get("blocked") or [])
    if license_id in approved:
        return "approved"
    if license_id in review:
        return "review_required"
    if license_id in blocked:
        return "blocked"
    return "unknown"

STATUS_RANK = {"approved": 0, "review_required": 1, "blocked": 2, "unknown": 3}


def resolve_status(raw_license: str, policy: dict[str, Any]) -> tuple[str, str]:
    """Resolve a (possibly compound) SPDX-ish license string to a policy
    status. Returns (status, normalized_license_id_used_for_status).

    For 'AND' expressions every component must independently be approved
    for the whole to count as approved (you're bound by all of them). For
    'OR' expressions the *best* (lowest-risk) component's status wins,
    since the licensee may choose which term to comply with — reflecting
    how dual/multi-licensing actually works.
    """
    op, tokens = split_spdx_expression(raw_license)
    tokens = [normalize_license(t) for t in tokens]

    if op == "SINGLE":
        status = classify(tokens[0], policy)
        return status, tokens[0]

    statuses = [classify(t, policy) for t in tokens]
    if op == "AND":
        worst = max(statuses, key=lambda s: STATUS_RANK[s])
        return worst, raw_license
    # OR
    best = min(statuses, key=lambda s: STATUS_RANK[s])
    return best, raw_license


def load_direct_names(direct_inventory: dict[str, Any]) -> dict[str, set[str]]:
    """Return {'pypi': {names...}, 'npm': {names...}} of our hand-tracked
    direct dependencies, for cross-referencing the `direct` flag."""
    result: dict[str, set[str]] = {"pypi": set(), "npm": set()}
    for dep in direct_inventory.get("dependencies") or []:
        eco = dep.get("ecosystem")
        name = dep.get("name")
        if eco in result and name:
            result[eco].add(name.lower())
    return result


def pip_licenses_to_entries(
    data: list[dict[str, Any]], *, scope: str, direct_names: set[str]
) -> list[dict[str, Any]]:
    entries = []
    for pkg in data:
        name = pkg["Name"]
        if name.lower().replace("_", "-") in FIRST_PARTY_NAMES:
            continue
        entries.append(
            {
                "name": name,
                "ecosystem": "pypi",
                "version": pkg.get("Version", ""),
                "license_raw": pkg.get("License", "UNKNOWN") or "UNKNOWN",
                "scope": scope,
                "direct": name.lower() in direct_names,
            }
        )
    return entries


def license_checker_to_entries(
    data: dict[str, Any], *, scope: str, direct_names: set[str]
) -> list[dict[str, Any]]:
    entries = []
    for key, info in data.items():
        # key is "name@version", but scoped packages look like "@scope/name@version"
        match = re.match(r"^(.*)@([^@]+)$", key)
        if not match:
            continue
        name, version = match.group(1), match.group(2)
        if name in FIRST_PARTY_NAMES:
            continue
        entries.append(
            {
                "name": name,
                "ecosystem": "npm",
                "version": version,
                "license_raw": str(info.get("licenses", "UNKNOWN") or "UNKNOWN"),
                "scope": scope,
                "direct": name.lower() in direct_names,
            }
        )
    return entries


def dedupe_prefer_runtime(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The 'dev'/'all' scans are supersets of the 'runtime'/'prod' scans for
    a given ecosystem. Keep one row per (ecosystem, name, version), tagging
    scope='runtime' if it appeared in the production-only scan, else 'dev'.
    """
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in entries:
        key = (e["ecosystem"], e["name"], e["version"])
        if key not in by_key:
            by_key[key] = e
        elif e["scope"] == "runtime":
            by_key[key]["scope"] = "runtime"
    return list(by_key.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pip-prod", type=Path, required=True)
    parser.add_argument("--pip-dev", type=Path, required=True)
    parser.add_argument("--npm-prod", type=Path, required=True)
    parser.add_argument("--npm-all", type=Path, required=True)
    args = parser.parse_args()

    policy = load_yaml(POLICY_FILE)
    direct_inventory = load_yaml(DIRECT_INVENTORY_FILE)
    direct_names = load_direct_names(direct_inventory)

    pip_prod = pip_licenses_to_entries(
        load_json(args.pip_prod), scope="runtime", direct_names=direct_names["pypi"]
    )
    pip_dev = pip_licenses_to_entries(
        load_json(args.pip_dev), scope="dev", direct_names=direct_names["pypi"]
    )
    npm_prod = license_checker_to_entries(
        load_json(args.npm_prod), scope="runtime", direct_names=direct_names["npm"]
    )
    npm_all = license_checker_to_entries(
        load_json(args.npm_all), scope="dev", direct_names=direct_names["npm"]
    )

    pip_entries = dedupe_prefer_runtime(pip_prod + pip_dev)
    npm_entries = dedupe_prefer_runtime(npm_prod + npm_all)

    all_entries = sorted(pip_entries + npm_entries, key=lambda e: (e["ecosystem"], e["name"]))

    offenders = []
    for e in all_entries:
        override = PACKAGE_LICENSE_OVERRIDES.get((e["ecosystem"], e["name"]))
        license_raw = override if override else e["license_raw"]
        status, resolved_license = resolve_status(license_raw, policy)
        e["license"] = resolved_license
        e["approval_status"] = status
        if override:
            e["note"] = "License disambiguated via manual PyPI/registry verification (see PACKAGE_LICENSE_OVERRIDES in this script)."
        del e["license_raw"]
        if status in ("blocked", "unknown"):
            offenders.append(e)

    counts = {"approved": 0, "review_required": 0, "blocked": 0, "unknown": 0}
    for e in all_entries:
        counts[e["approval_status"]] += 1

    output = {
        "_generated_by": "compliance/generate_transitive_inventory.py — do not hand-edit",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "_note": (
            "Full resolved dependency tree (direct + transitive) for both "
            "ecosystems. 'scope: runtime' means the package appears in a "
            "production-only install (backend: `pip install .` with no "
            "[dev] extra; frontend: `npm ls --production`) and therefore "
            "ships in the actual Docker runtime image / built bundle. "
            "'scope: dev' means it was only found in the full dev/build "
            "tree (lint/test/build tooling) and is never shipped."
        ),
        "summary": counts,
        "dependencies": all_entries,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(output, fh, sort_keys=False, width=100)

    print(f"Wrote {OUTPUT_FILE} ({len(all_entries)} resolved packages)")
    print(f"  approved:        {counts['approved']}")
    print(f"  review_required: {counts['review_required']}")
    print(f"  blocked:         {counts['blocked']}")
    print(f"  unknown:         {counts['unknown']}")

    if offenders:
        print("\nBLOCKED/UNKNOWN transitive packages:")
        for o in offenders:
            print(f"  - [{o['ecosystem']}] {o['name']}@{o['version']} "
                  f"license={o['license']!r} scope={o['scope']} status={o['approval_status']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
