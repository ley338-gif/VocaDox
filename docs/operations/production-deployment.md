# Production deployment

VocaDox ships separate Compose definitions for local development and a
single-host production deployment. `deploy/compose.prod.yml` is fail-closed:
only the TLS reverse proxy publishes ports, required paths and the database
password have no defaults, and every application process starts with
`VOCADOX_ENVIRONMENT=production`.

This is an operator-managed, on-premise deployment. It does not obtain or
renew certificates, configure DNS/firewalls, copy backups off-host, or install
AI models automatically.

## Prerequisites

- A supported Docker Engine with Docker Compose v2.
- DNS for the intended VocaDox hostname.
- A PEM certificate chain and matching private key readable by Docker.
- A dedicated absolute backup directory, preferably on separately protected or
  off-host-backed storage.
- Host firewall rules that expose only the intended HTTP/HTTPS ports. Do not
  publish PostgreSQL (`5432`), Valkey (`6379`), backend (`8000`), or frontend
  container ports separately.

## Configure and validate

Keep the real environment file outside the repository and readable only by the
deployment administrator:

```sh
sudo install -d -m 0700 /etc/vocadox /var/backups/vocadox
sudo install -m 0600 deploy/production.env.example /etc/vocadox/production.env
sudo editor /etc/vocadox/production.env
```

Generate a URL-safe database password, for example with
`openssl rand -hex 32`, and set the three required values:

- `POSTGRES_PASSWORD`
- `VOCADOX_BACKUP_PATH`
- `VOCADOX_TLS_CERTIFICATE_PATH` and `VOCADOX_TLS_PRIVATE_KEY_PATH`

The database password is embedded into the internal SQLAlchemy URL. Use a
URL-safe value such as random hexadecimal text; do not paste punctuation that
has special meaning in a URL.

Validate interpolation and structure before creating containers:

```sh
docker compose \
  --env-file /etc/vocadox/production.env \
  -f deploy/compose.prod.yml config --quiet
```

Empty required values fail here. Unsafe application combinations fail in the
one-shot `config-check` container before migrations or application services
start. Production rejects insecure session cookies, database echo, missing or
known-default/short database passwords, wildcard CORS, and non-HTTPS CORS
origins. `VOCADOX_PRODUCTION_CORS_ALLOW_ORIGINS` deliberately has a different
name from the development setting so Compose cannot inherit a localhost grant
from the repository-root `.env`. An empty list is the recommended same-origin
setting. Validation errors name the unsafe setting without echoing its secret
input value.

## Start and verify

```sh
docker compose \
  --env-file /etc/vocadox/production.env \
  -f deploy/compose.prod.yml up -d --build

docker compose \
  --env-file /etc/vocadox/production.env \
  -f deploy/compose.prod.yml ps

curl --fail https://vocadox.example/health
curl --fail https://vocadox.example/health/ready
```

`config-check` and `migrate` should show successful completion. PostgreSQL and
Valkey are attached only to the internal `data` network. The backend and static
frontend are reachable only through the TLS proxy. Plain HTTP redirects to
HTTPS, except for the local proxy health endpoint.

Create the first administrator explicitly:

```sh
docker compose \
  --env-file /etc/vocadox/production.env \
  -f deploy/compose.prod.yml exec backend \
  python -m app.identity.bootstrap_admin \
  --username admin --display-name Administrator --email admin@example.org
```

## Backups and restore tooling

The production stack bind-mounts `VOCADOX_BACKUP_PATH` at `/app/backups`,
separate from the named database/media/model volumes. Run the existing tool
profile with the same environment file:

```sh
docker compose \
  --env-file /etc/vocadox/production.env \
  -f deploy/compose.prod.yml --profile tools run --rm backup create
```

The bind mount alone is not an off-host backup. Follow
`docs/operations/disaster-recovery.md` for encryption, copying, restore tests,
RPO/RTO, and the limitations of application rollback after a migration.

## Operational boundaries

- TLS material is mounted read-only; renewal and proxy reload remain operator
  responsibilities.
- The production file builds from the checked-out, locked source tree. Release
  artifact publication and signing are separate release-process concerns.
- The outbound-capable `egress` network is limited to the extraction worker and
  model-manager. It supports an administrator-selected local Ollama endpoint
  and explicit model installation; VocaDox adds no cloud service or telemetry.
- GPU device reservations remain deployment-specific; see `gpu-runtime.md`.
- A load balancer, WAF, host monitoring, and off-host backup transport are not
  bundled. Their absence must be considered in the operator's risk assessment.

For local development, continue to use the root `docker compose` command, which
wraps `deploy/compose.dev.yml`; its published service ports and development
defaults are intentionally not suitable for production.
