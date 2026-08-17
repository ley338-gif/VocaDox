# Fonts & Icon Assets

This page documents the licenses for the two bundled visual-asset packages
used by the VocaDox frontend: the Inter font (via `@fontsource/inter`) and
the Lucide icon set (via `lucide-react`). Both were verified live against
their registry metadata; see `compliance/dependency-inventory.yml` for the
raw lookup sources.

## Inter font — `@fontsource/inter`

- **Package license (npm registry):** `OFL-1.1` (verified — matches
  expectation)
- **Source checked:** `https://registry.npmjs.org/@fontsource/inter/latest`,
  version `5.3.0`
- **Underlying font license:** Inter itself (designed by Rasmus Andersson)
  is published under the [SIL Open Font License 1.1](https://openfontlicense.org/).
  `@fontsource/inter` simply repackages the OFL-licensed font files for npm
  consumption; the font's license does not change in that repackaging.
- **What OFL-1.1 permits:** free use, study, modification, and
  redistribution, including bundling in a commercial, closed-source
  application, as long as the font (including any modified versions) is
  not sold on its own separately from the application, and any
  redistributed/modified font files keep the OFL license and are not
  distributed under the "Inter" reserved font name if modified without
  permission. VocaDox uses the font unmodified as a webfont asset, which
  is squarely within OFL-1.1's intended use case.
- **Policy bucket:** `approved` (see `compliance/license-policy.yml`).

## Lucide icon set — `lucide-react`

- **Package license (npm registry):** `ISC` (verified — matches
  expectation)
- **Source checked:** `https://registry.npmjs.org/lucide-react/latest`,
  version `1.31.0`
- **Upstream project license:** The Lucide project (the fork of Feather
  Icons that `lucide-react` is generated from) is itself licensed under
  ISC for its icon source files and tooling, consistent with the
  `lucide-react` package license above.
- **What ISC permits:** functionally equivalent to the MIT license —
  free use, modification, and redistribution (including in closed-source
  commercial software), with only a copyright/license notice
  preservation requirement.
- **Policy bucket:** `approved` (see `compliance/license-policy.yml`).

## Summary

| Asset | Package | License | Status |
|---|---|---|---|
| Inter font | `@fontsource/inter` v5.3.0 | OFL-1.1 | approved |
| Lucide icons | `lucide-react` v1.31.0 | ISC | approved |

Both assets are safe to bundle in VocaDox's on-premise, closed-source
distribution with no copyleft or redistribution obligations beyond
standard notice/attribution preservation.
