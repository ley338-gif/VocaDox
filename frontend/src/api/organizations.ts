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
