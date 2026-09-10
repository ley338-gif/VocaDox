# Dependency management

VocaDox treats dependency resolution as reviewed source code. Python uses
committed `uv.lock` files; Node uses `frontend/package-lock.json`. Developer
machines, CI, compliance jobs, and container builds install from those files
with locked/frozen commands.

## Python

Install uv 0.12.12, the version required by each `pyproject.toml`. From the
relevant Python project directory:

```sh
uv sync --locked --extra dev       # backend or connector development
uv sync --locked                   # production dependencies only
uv sync --locked --extra ai        # backend AI worker, CPU PyTorch wheels
uv lock --check                    # verify pyproject.toml and uv.lock agree
```

The backend and the standalone GDT bridge intentionally have separate locks
because they have separate build contexts and release artifacts. Backend
PyTorch packages are explicitly sourced from the official CPU wheel index;
do not replace this with an unqualified extra index.

To update dependencies, edit the relevant `pyproject.toml`, run `uv lock`,
review both direct and transitive changes, then run that project's complete
checks. Update the compliance inventories whenever the resolved tree changes.

## Node

From `frontend/`, use `npm ci` for normal installs. It fails when
`package.json` and `package-lock.json` disagree. To make an intentional update,
use the npm version declared in `packageManager`, update `package.json`, run
`npm install`, review `package-lock.json`, and run lint, typecheck, tests,
build, audit, and license checks.

Never add an `npm ci || npm install` fallback: that converts lockfile drift
from a visible error into an unreviewed dependency update.
