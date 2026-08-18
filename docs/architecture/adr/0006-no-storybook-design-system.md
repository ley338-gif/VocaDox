# 0006 — No-Storybook design-system approach (CSS variables + demo route)

## Status
Accepted

## Context
The Stylesystem reference defines a full token set (colors, type scale,
spacing, radius, shadows) and component states (buttons, form controls,
badges, cards, ...). A living style guide is valuable for keeping the UI
consistent, but Storybook is a heavyweight addition (its own build
pipeline, addon ecosystem, extra CI job) for a Phase 0 scaffold with no
component library yet.

## Decision
Encode all design tokens as CSS custom properties in
`frontend/src/styles/tokens.css`, and render a `/design-system` route
(`frontend/src/design-system/DesignSystemPage.tsx`) inside the actual app
that displays every token and component state directly from those
variables — colors, typography scale, spacing/radius/shadow swatches,
button variants, form controls, badges/tags/status dots, and card/list
examples. No Storybook, no separate build target.

## Consequences
- One less toolchain to maintain, configure, and keep in CI; the style
  guide can never drift from the CSS variables the app actually uses,
  because it consumes the same `tokens.css`.
- No isolated component "playground" with per-story controls/knobs the way
  Storybook provides — acceptable for Phase 0's scope (no component
  library yet beyond the design-system primitives themselves).
- Revisit if the component inventory grows large enough that an isolated
  dev environment becomes worth the overhead.
