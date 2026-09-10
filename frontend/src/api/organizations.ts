import { ApiError } from "./client";

const API_PREFIX = "/api/v1";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  description: string | null;
}

export async function listMyOrganizations(): Promise<Organization[]> {
  const response = await fetch(`${API_PREFIX}/organizations`, { credentials: "include" });
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText);
  }
  return (await response.json()) as Organization[];
}

/** Deliberately minimal (post-GA): backs the conversation-participant
 * "pick a registered user" directory -- no e-mail, auth-provider, or
 * group data, see backend `OrganizationMemberUserResponse`. */
export interface OrganizationMemberUser {
  id: string;
  username: string;
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  avatar_asset_key: string | null;
}

export async function listOrganizationMemberUsers(
  organizationId: string
): Promise<OrganizationMemberUser[]> {
  const response = await fetch(`${API_PREFIX}/organizations/${organizationId}/member-users`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText);
  }
  return (await response.json()) as OrganizationMemberUser[];
}
