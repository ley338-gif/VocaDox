# License Policy

VocaDox is distributed and deployed on-premise, as closed-source software,
to customers who do not receive the source code. Because of that, our main
concern with third-party licenses is not "can we use this at all" but
"does using this create an obligation to disclose or relicense our own
source code, or to open-source modifications." This page is the
human-readable companion to `compliance/license-policy.yml` (spec §10);
the YAML file is the source of truth enforced by
`compliance/check_licenses.py`.

## Approved

`MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `PostgreSQL`,
`OFL-1.1`.

These are all permissive licenses. They allow use, modification, and
redistribution — including inside closed-source, commercial, on-premise
software — with essentially no obligations beyond preserving the
copyright/license notice. None of them require us to disclose or
relicense VocaDox's own source code. `OFL-1.1` is included specifically
for font assets (see `docs/licenses/fonts-assets.md`); it carries a
narrow "don't sell the font by itself" restriction that doesn't apply to
using it as a bundled application asset.

## Review required

`MPL-2.0`, `LGPL-2.1`, `LGPL-2.1-or-later`, `LGPL-3.0`,
`LGPL-3.0-or-later`.

These are weak-copyleft licenses. Their copyleft obligation is scoped to
the file (MPL-2.0) or to the library itself (LGPL) — using them
unmodified as a dynamically-linked/imported dependency generally does not
force VocaDox's own code to be relicensed. However, the exact obligations
depend on how the dependency is integrated (static vs. dynamic linking,
whether we patch it, how it's distributed), so any dependency in this
bucket requires a human to look at the specific integration and either:

- record an explicit exception in `compliance/exceptions.yml` with a
  reason and approver, or
- avoid the dependency in favor of an approved-bucket alternative.

For example, in Phase 0 we deliberately chose `asyncpg` (Apache-2.0) over
`psycopg` (LGPL-3.0) for the async Postgres driver, avoiding the need for
a review in the first place.

## Blocked

`GPL-2.0`, `GPL-3.0`, `AGPL-3.0`, `SSPL-1.0`, `RSAL`, `BSL-1.1`,
`Commons-Clause`, `proprietary`, `UNKNOWN`.

These are never permitted as direct dependencies without an explicit,
recorded exception:

- **GPL-2.0 / GPL-3.0** are strong copyleft licenses that, depending on
  how they're linked, can require VocaDox's own source to be released
  under the same terms — incompatible with a closed-source on-premise
  product.
- **AGPL-3.0** extends that copyleft trigger to network use, which is
  especially dangerous for a server-side product like VocaDox.
- **SSPL-1.0, RSAL, BSL-1.1, and "Commons-Clause"-modified licenses** are
  "source-available" rather than genuinely open-source: they impose
  commercial-use or hosting restrictions that can directly conflict with
  running VocaDox as a paid on-premise product.
- **proprietary** licenses need a commercial agreement and legal review
  before any use, not a routine dependency approval.
- **UNKNOWN** means we could not determine the license at all — treated
  as blocked until it is actually identified, never assumed to be safe.

## Enforcement

`compliance/check_licenses.py` loads `compliance/license-policy.yml`
together with `compliance/dependency-inventory.yml` and
`compliance/model-inventory.yml`, classifies every entry, prints a
summary, and exits with a non-zero status if anything resolves to
`blocked` or `unknown`. It is intended to be run in CI as a gate on every
change to the dependency or model inventories.
