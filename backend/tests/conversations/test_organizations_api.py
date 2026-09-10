from __future__ import annotations

from app.identity.service import (
    add_user_to_group,
    assign_role_to_group,
    create_local_user,
    get_or_create_group,
    get_role_by_name,
    update_user,
)
from app.organizations.models import Organization, OrganizationMembership
from httpx import AsyncClient
from sqlalchemy import select

from tests.conversations.conftest import login


async def test_user_only_sees_own_organizations(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    response = await client.get("/api/v1/organizations", headers=headers)
    assert response.status_code == 200
    org_ids = {org["id"] for org in response.json()}
    assert org_ids == {seeded["org_a"]}


async def test_admin_sees_all_organizations(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    response = await client.get("/api/v1/organizations", headers=headers)
    assert response.status_code == 200
    org_ids = {org["id"] for org in response.json()}
    assert org_ids == {seeded["org_a"], seeded["org_b"]}


async def test_organizations_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/organizations")
    assert response.status_code == 401


# -- GET /organizations/{id}/member-users (post-GA directory endpoint) -----


async def test_member_users_returns_active_org_members_with_permission(
    client: AsyncClient, seeded: dict, app_env
) -> None:
    """alice (User role, which now grants user:read-directory) can list
    org_a's directory; it includes herself, excludes an inactive
    colleague, and never leaks e-mail."""
    _, sessionmaker = app_env
    async with sessionmaker() as session:
        user_role = await get_role_by_name(session, "User")
        assert user_role is not None
        org_a = (
            await session.execute(select(Organization).where(Organization.slug == "org-a"))
        ).scalar_one()

        inactive = await create_local_user(
            session,
            username="inactive-colleague",
            password="a strong enough password 999",
            display_name="Inactive Colleague",
        )
        group = await get_or_create_group(session, name="Org A Clinicians (inactive)")
        await assign_role_to_group(session, group_id=group.id, role_id=user_role.id)
        await add_user_to_group(session, user_id=inactive.id, group_id=group.id)
        session.add(OrganizationMembership(user_id=inactive.id, organization_id=org_a.id))
        await update_user(session, inactive, is_active=False)
        await session.commit()

    headers = await login(client, "alice", "a very strong password 123")
    response = await client.get(
        f"/api/v1/organizations/{seeded['org_a']}/member-users", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    usernames = {u["username"] for u in body}
    assert "alice" in usernames
    assert "inactive-colleague" not in usernames  # inactive users are excluded
    for item in body:
        assert "email" not in item  # deliberately minimal: no e-mail leak
        assert set(item.keys()) == {
            "id",
            "username",
            "display_name",
            "first_name",
            "last_name",
            "avatar_asset_key",
        }


async def test_member_users_requires_read_directory_permission(
    client: AsyncClient, seeded: dict, app_env
) -> None:
    """A role without `user:read-directory` (e.g. Reviewer) is rejected —
    genuine permission-based RBAC, not just organization membership."""
    _, sessionmaker = app_env
    async with sessionmaker() as session:
        reviewer_role = await get_role_by_name(session, "Reviewer")
        assert reviewer_role is not None
        org_a = (
            await session.execute(select(Organization).where(Organization.slug == "org-a"))
        ).scalar_one()

        frank = await create_local_user(
            session,
            username="frank",
            password="a strong enough password 888",
            display_name="Frank",
        )
        group = await get_or_create_group(session, name="Org A Reviewers")
        await assign_role_to_group(session, group_id=group.id, role_id=reviewer_role.id)
        await add_user_to_group(session, user_id=frank.id, group_id=group.id)
        session.add(OrganizationMembership(user_id=frank.id, organization_id=org_a.id))
        await session.commit()

    headers = await login(client, "frank", "a strong enough password 888")
    response = await client.get(
        f"/api/v1/organizations/{seeded['org_a']}/member-users", headers=headers
    )
    assert response.status_code == 403, response.text


async def test_member_users_rejects_non_member_without_system_admin(
    client: AsyncClient, seeded: dict
) -> None:
    """bob has `user:read-directory` (User role) but is a member of org_b,
    not org_a — reading org_a's directory must still be rejected."""
    headers = await login(client, "bob", "another very strong pw 456")
    response = await client.get(
        f"/api/v1/organizations/{seeded['org_a']}/member-users", headers=headers
    )
    assert response.status_code == 403, response.text


async def test_member_users_admin_bypasses_membership_check(
    client: AsyncClient, seeded: dict
) -> None:
    """carol (System Admin) may read any organization's directory despite
    not being a formal member — same bypass posture as every other
    organization-scoped endpoint."""
    headers = await login(client, "carol", "yet another strong pw 789")
    response = await client.get(
        f"/api/v1/organizations/{seeded['org_a']}/member-users", headers=headers
    )
    assert response.status_code == 200, response.text
