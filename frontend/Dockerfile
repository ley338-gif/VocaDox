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
FROM nginx:1.27.3-alpine3.20@sha256:814a8e88df978ade80e584cc5b333144b9372a8e3c98872d07137dbf3b44d0e4 AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
