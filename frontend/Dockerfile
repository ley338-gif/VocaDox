# Pinned base images (see compliance/container-inventory.yml for license/digest record).
FROM node:20.18.1-bookworm-slim@sha256:b2c8e0eb8a6aeeae33b2711f8f516003e27ee45804e270468d937b3214f2f0cc AS base
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

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
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
