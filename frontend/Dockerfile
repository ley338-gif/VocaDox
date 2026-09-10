# Pinned base images (see compliance/container-inventory.yml for license/digest record).
#
# node:22-alpine3.24 (not the originally scaffolded node:20.18.1-bookworm-slim):
# a Trivy scan during Phase 0 final closeout found 8 CRITICAL / 48 HIGH on
# the bookworm image (mostly perl-base — same irreducible-on-Debian issue
# as the backend's original base image, plus npm's own vendored
# tar/brace-expansion/etc.). Evaluated node:22-bookworm-slim (6 CRITICAL,
# still has perl-base), node:22-trixie-slim (5 CRITICAL, perl-base again —
# Debian ships perl on every release), and node:22-alpine3.21/3.22/3.24
# (5 CRITICAL each, purely npm's own vendored deps — Alpine doesn't ship
# perl at all). alpine3.24 + applying current Alpine security fixes and
# upgrading npm's own bundled copy of itself (see below) gets this to
# 0 CRITICAL / 0 HIGH — see ADR-0008 and
# container-inventory.yml for the full comparison and final disposition.
FROM node:22-alpine3.24@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS base
WORKDIR /app

# The image digest is immutable, but Alpine publishes security-fixed package
# revisions between image refreshes. Apply those fixes before installing any
# build tooling; the resulting dev/build stage is scanned in CI as well.
RUN apk upgrade --no-cache

# npm ships its own vendored copies of tar/brace-expansion/ip-address/etc.
# inside the Node image (used by npm itself, not our app) — the versions
# bundled with the base image's npm were the source of every CRITICAL
# Trivy finding on this image. Keep the remediated npm release explicit so
# an identical source tree never resolves a different build tool.
ARG NPM_VERSION=11.19.1
RUN npm install -g "npm@${NPM_VERSION}" && npm cache clean --force

COPY package.json package-lock.json ./
RUN npm ci

# --- dev target: used ONLY by deploy/docker-compose.yml for local development.
# Runs the Vite dev server. Never used as the production runtime. ---
FROM base AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- build target: compiles static production assets ---
FROM base AS build
COPY . .
RUN npm run build

# --- runtime target: production image. Serves the static build output via
# nginx — the Vite dev server MUST NOT run in production. ---
# Pinned to alpine3.24 (not the originally scaffolded alpine3.20): a Trivy
# scan during Phase 0 remediation flagged alpine3.20 as EOL ("no longer
# supported by the distribution" — security patches had stopped), which is
# why its Alpine-packaged libssl/libxml2/libpng/musl/etc. all showed
# unfixed HIGH/CRITICAL CVEs despite fixes existing upstream. alpine3.24 is
# the current supported release and carries none of those findings.
FROM nginx:1.31.3-alpine3.24@sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752 AS runtime
RUN apk upgrade --no-cache
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
