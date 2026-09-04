# Admin docs

**Phase 9 status: Timeline/external-reference grouping, deterministic
Conversation Comparison, and Follow-ups/Tasks are now implemented** — see
`docs/architecture/domain-model.md`'s "Phase 9: Longitudinal Documentation"
section. **Phase 8 status: Analytics, the Evaluation Lab, and Model
Lifecycle are now implemented** — see `analytics-evaluation.md`. **Phase 7
status: the
Admin Portal (`/admin`) is implemented** — see `admin-portal.md` for the
full navigation/section reference. This page keeps the Phase 1 bootstrap
procedure below, since every admin action (creating more users, managing
groups/roles, ...) still depends on having a first System Admin account
to log in as.

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
reach the full `/admin` portal — see `admin-portal.md`.

## Roles and permissions

Seeded roles and what each grants are defined in
`backend/app/identity/seed.py` (`ROLES`, `PERMISSIONS`) — System Admin,
Manager, Template Manager, Reviewer, User, Auditor, API Service Account,
matching the product spec's role list exactly. As of Phase 7, every
permission referenced by an Admin Portal page has a real enforcement
point; `retention:read`/`retention:write` are new this phase (Manager +
System Admin). See `admin-portal.md` for the full page-by-page
permission reference.

**Upgrading an existing (pre-Phase-7) installation**: run
`alembic upgrade head` (Phase 7 added no new tables/columns, so this is
frequently a no-op) followed by `python -m app.identity.seed` (or
`docker compose exec backend python -m app.identity.seed`) to pick up the
new `retention:read`/`retention:write` permission codes — idempotent,
safe to run on every upgrade, same pattern as every prior phase's RBAC
seed update.

**Upgrading an existing (pre-Phase-8) installation**: Phase 8 DOES add a
new migration (`0009_analytics_evaluation`: `model_profiles
.lifecycle_status`, `model_profile_lifecycle_events`, `evaluation_runs`).
Run `alembic upgrade head` then `python -m app.identity.seed` to pick up
the new `evaluation:run`/`model-profile:promote` permission codes
(`analytics:read`, seeded since Phase 1, already gates the read-only
analytics/evaluation views — no new "read" permission was needed).

**Upgrading an existing (pre-Phase-9) installation**: Phase 9 DOES add a
new migration (`0010_longitudinal_documentation`: `follow_up_tasks`). Run
`alembic upgrade head` then `python -m app.identity.seed` to pick up the
new `timeline:read`/`task:read`/`task:create`/`task:update` permission
codes (granted to Manager/Reviewer/User/Auditor as appropriate — see
`backend/app/identity/seed.py`'s `ROLES`).

Additional users/groups/organizations/role assignments are now managed
through the Admin Portal UI (`/admin/users`, `/admin/groups`,
`/admin/organizations`) or its underlying REST API — the Phase 1 "requires
a Python shell against the running environment" limitation is resolved.
