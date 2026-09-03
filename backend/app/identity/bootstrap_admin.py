"""One-time CLI to create the first System Admin user.

Per spec §66: no direct DB manipulation for creating the initial admin.
Run as:

    python -m app.identity.bootstrap_admin --username admin \\
        --password '<strong password>' --display-name "Administrator" \\
        --email admin@example.org

Refuses to run if any user already holds the System Admin role, unless
`--force` is passed — this is the "can't be silently reused" guard the
spec requires. `--force` is a deliberate, explicit escape hatch for
disaster recovery (e.g. all admin accounts lost); it does NOT bypass the
uniqueness of usernames/emails, only the "an admin already exists" check.

The password is read from the `--password` flag or, if omitted, prompted
interactively via `getpass` (never echoed, never logged, never accepted
via a plain positional argument that would land in shell history by
default — though `--password` is provided for scripted bootstrap and its
caller is responsible for shell-history hygiene in that case).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from app.identity.models import Role
from app.identity.passwords import MIN_PASSWORD_LENGTH
from app.identity.seed import apply_seed
from app.identity.service import (
    add_user_to_group,
    any_user_has_role,
    assign_role_to_group,
    create_local_user,
    get_or_create_group,
    get_role_by_name,
    get_user_by_username,
)
from app.platform.db import model_registry  # noqa: F401 - registers all domain models
from app.platform.db.session import get_sessionmaker
from app.profiles.seed import apply_seed as apply_model_profile_seed

SYSTEM_ADMIN_ROLE = "System Admin"
BOOTSTRAP_GROUP_NAME = "Administrators"


async def bootstrap_admin(
    *,
    username: str,
    password: str,
    display_name: str,
    email: str | None,
    force: bool,
) -> int:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await apply_seed(session)
        await apply_model_profile_seed(session)  # Phase 4: default extraction ModelProfile
        await session.commit()

        already_has_admin = await any_user_has_role(session, SYSTEM_ADMIN_ROLE)
        if already_has_admin and not force:
            print(
                "Refusing to bootstrap: a System Admin user already exists. "
                "Pass --force to add another admin anyway.",
                file=sys.stderr,
            )
            return 1

        if await get_user_by_username(session, username) is not None:
            print(f"Refusing to bootstrap: username {username!r} already exists.", file=sys.stderr)
            return 1

        role: Role | None = await get_role_by_name(session, SYSTEM_ADMIN_ROLE)
        if role is None:
            print(
                "Refusing to bootstrap: System Admin role not found after seeding.",
                file=sys.stderr,
            )
            return 1

        user = await create_local_user(
            session,
            username=username,
            password=password,
            display_name=display_name,
            email=email,
        )
        group = await get_or_create_group(
            session,
            name=BOOTSTRAP_GROUP_NAME,
            description="System administrators (bootstrap-managed).",
        )
        await assign_role_to_group(session, group_id=group.id, role_id=role.id)
        await add_user_to_group(session, user_id=user.id, group_id=group.id)

        await session.commit()

    print(f"Created System Admin user {username!r} (id={user.id}).")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--email", default=None)
    parser.add_argument(
        "--password",
        default=None,
        help="If omitted, prompted interactively (recommended).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bootstrap another admin even if one already exists.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    password = args.password or getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1

    return asyncio.run(
        bootstrap_admin(
            username=args.username,
            password=password,
            display_name=args.display_name,
            email=args.email,
            force=args.force,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
