# Admin docs

Phase 1 status: no admin console UI exists yet (targeted for Phase 7 — see
`backend/app/administration/README.md`). What Phase 1 does add is the
initial-admin bootstrap procedure below, since every other identity/RBAC
admin action (creating more users, managing groups/roles, ...) depends on
having a first System Admin account to log in as.

## Bootstrapping the first System Admin user

Per the product spec, there is no direct database manipulation for
creating the first admin. Instead, run the bootstrap CLI once against a
running backend environment (it talks to Postgres/Valkey using the same
`VOCADOX_*` settings the API server uses):

```bash
# From backend/, with the venv active and VOCADOX_DATABASE_URL /
# VOCADOX_VALKEY_URL pointed at your environment:
python -m app.identity.bootstrap_admin \
  --username admin \
  --display-name "Administrator" \
  --email admin@example.org
# Password is prompted interactively (recommended) — or pass
# --password '<strong password>' for scripted/CI bootstrap, understanding
# that puts the password in that shell's history unless you take care of
# that yourself.
```

Under Docker Compose, run it inside the backend container:

```bash
docker compose exec backend python -m app.identity.bootstrap_admin \
  --username admin --display-name "Administrator" --email admin@example.org
```

What it does:

1. Idempotently seeds the baseline permissions and system roles (System
   Admin, Manager, Template Manager, Reviewer, User, Auditor, API Service
   Account) if they don't already exist — see `app.identity.seed`.
2. Refuses to run if any user already holds the System Admin role, unless
   you pass `--force` (an explicit escape hatch for disaster recovery,
   e.g. "all admin accounts were lost" — it does not bypass
   username/email uniqueness, only the "an admin already exists" check).
3. Creates the user (local auth, Argon2id-hashed password — minimum 12
   characters), an "Administrators" group if one doesn't exist, assigns
   the System Admin role to that group, and adds the new user to it.

After this, log in at `/login` with that username/password. The account
has every permission in the system (`system:admin` included), so it can
reach the `/admin`-gated route once that portal exists (Phase 7).

## Roles and permissions (Phase 1 data model)

Seeded roles and what each grants are defined in
`backend/app/identity/seed.py` (`ROLES`, `PERMISSIONS`) — System Admin,
Manager, Template Manager, Reviewer, User, Auditor, API Service Account,
matching the product spec's role list exactly. Only identity/organizations
permissions have real enforcement points so far
(`system:admin`, `user:manage`, `group:manage`, `organization:manage`,
`audit:read`); permissions for domains that don't exist yet
(`conversation:*`, `document:*`, `template:*`, ...) are seeded now so role
definitions are complete and stable, with enforcement landing alongside
each domain in later phases.

There is no admin UI yet to create additional users, groups, or role
assignments beyond the bootstrap flow above — that's the Phase 7 admin
portal's job. Until then, additional users/groups/role assignments require
direct use of the `app.identity.service` functions (e.g. via a Python
shell against the running environment), which is an accepted Phase 1
limitation, not a recommended pattern for production operation.
