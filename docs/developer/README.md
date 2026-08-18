# Developer docs

For setup, branch/PR workflow, and local lint/typecheck/test commands, see
the root [README.md](../../README.md) quickstart and
[CONTRIBUTING.md](../../CONTRIBUTING.md).

## Authentication/authorization (Phase 1)

### Where things live

- `backend/app/identity/models.py` — `User`, `Group`, `Role`,
  `Permission`, and the join tables (`UserGroupMembership`, `GroupRole`,
  `RolePermission`) that implement the RBAC resolution chain
  User → Group → Role → Permission.
- `backend/app/identity/passwords.py` — Argon2id hashing
  (`hash_password`/`verify_password`/`needs_rehash`); see
  [ADR-0010](../architecture/adr/0010-argon2-password-hashing.md).
- `backend/app/identity/auth_providers.py` — the `AuthProvider` interface
  (analogous to `app.providers`' pattern) and `LocalAuthProvider`, the
  only real implementation so far. `OIDC`/`LDAP_AD`/`REVERSE_PROXY` exist
  only as `AuthProviderType` enum values reserved for later phases.
- `backend/app/identity/sessions.py` — `SessionStore`, built on the
  existing `CacheBackend` Protocol (Valkey-backed) rather than a Postgres
  table; see [ADR-0009](../architecture/adr/0009-session-storage.md).
- `backend/app/identity/rbac.py` — `get_user_permissions` /
  `user_has_permission`: the *only* place permission resolution happens.
  Never compare a role or group name directly anywhere else in the
  codebase.
- `backend/app/identity/deps.py` — FastAPI dependencies:
  `get_current_user`, `require_permission(code)`, `require_csrf`. Every
  future domain router should depend on one of these (see the threat
  model's "Auth boundaries" section — authenticated by default).
- `backend/app/identity/router.py` — `POST /api/v1/auth/login`,
  `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`.
- `backend/app/identity/seed.py` — baseline permissions and the seeded
  system roles; `apply_seed` is idempotent.
- `backend/app/identity/bootstrap_admin.py` — the one-time first-admin CLI
  (see `docs/admin/README.md`).

### Adding a new authenticated/permission-gated endpoint

```python
from fastapi import APIRouter, Depends
from app.identity.deps import get_current_user, require_permission
from app.identity.models import User

router = APIRouter()

@router.get("/whatever")
async def whatever(user: User = Depends(get_current_user)) -> ...:
    ...  # any authenticated user

@router.post("/whatever")
async def create_whatever(
    user: User = Depends(require_permission("whatever:create")),
) -> ...:
    ...  # only callers with the whatever:create permission
```

For any state-changing endpoint reachable with just the session cookie
(i.e. anything that isn't naturally protected by also requiring a
just-issued CSRF token, like login itself), add
`dependencies=[Depends(require_csrf)]` to the route decorator — see
`POST /auth/logout` in `router.py` for the pattern.

### Adding a new permission or role

Add the permission code to `PERMISSIONS` and wire it into the relevant
role(s) in `ROLES`, both in `backend/app/identity/seed.py`. `apply_seed`
only inserts rows that don't already exist by name/code, so it's safe to
run repeatedly (it runs automatically at the start of
`bootstrap_admin`). There is no migration needed for new permissions/role
grants — they're seed data, not schema.

### Frontend

- `frontend/src/api/client.ts` — thin `fetch` wrapper for the three auth
  endpoints. `credentials: "include"` is required on every call so the
  httponly session cookie round-trips.
- `frontend/src/auth/context.ts` + `AuthContext.tsx` + `useAuth.ts` — the
  auth context/provider/hook, split into three files specifically so
  `useAuth`/`AuthContext` (non-component exports) don't live in the same
  file as the `AuthProvider` component (keeps Vite Fast Refresh happy —
  see `react-refresh/only-export-components`).
- `frontend/src/auth/RequireAuth.tsx` — `RequireAuth` (any authenticated
  user) and `RequirePermission` (gated on a specific permission code, e.g.
  `system:admin` for `/admin`) route guards.
- Same-origin API calls by design: the SPA calls relative `/api/v1/...`
  paths, proxied to the backend by Vite's dev server
  (`vite.config.ts`, `VITE_BACKEND_URL`) in development and by nginx
  (`nginx.conf`'s `/api/` location) in the production image — see the
  comments in both files for why (avoids CORS-credential plumbing; the
  session cookie stays same-origin either way).

### Running the identity tests

```bash
cd backend
pytest tests/identity -v
```

These use an in-memory SQLite database (`tests/identity/conftest.py`) and
an in-process fake `CacheBackend` — no Postgres/Valkey required, matching
the existing "no external services needed at test time" convention. The
Alembic migration itself (`0002_identity_rbac.py`) is verified separately
against a real Postgres — see `PHASE_1_VALIDATION_REPORT.md`'s
Reproducibility section for the exact commands.
