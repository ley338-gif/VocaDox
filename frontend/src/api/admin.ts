/**
 * Typed client for the Phase 7 Admin Portal's backend surface: Users,
 * Groups, Roles, Organizations, Audit, Dashboard, Models, Jobs, Workers,
 * Storage, Retention, About & Licenses. Same plain-fetch pattern as
 * api/conversations.ts / api/templates.ts / api/profiles.ts.
 */

import { ApiError } from "./client";

const API_PREFIX = "/api/v1";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, { ...init, credentials: "include" });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown, csrfToken: string): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  };
}

// -- Users / Groups / Roles --------------------------------------------

export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  auth_provider: string;
  is_active: boolean;
}

export interface AdminUserDetail extends AdminUser {
  group_ids: string[];
}

export function listUsers(): Promise<AdminUser[]> {
  return request("/admin/users");
}

export function getUser(userId: string): Promise<AdminUserDetail> {
  return request(`/admin/users/${userId}`);
}

export function createUser(
  payload: {
    username: string;
    password: string;
    display_name: string;
    email?: string | null;
    group_ids?: string[];
  },
  csrfToken: string
): Promise<AdminUserDetail> {
  return request("/admin/users", jsonInit("POST", payload, csrfToken));
}

export function updateUser(
  userId: string,
  payload: Partial<{
    display_name: string;
    email: string | null;
    is_active: boolean;
    group_ids: string[];
  }>,
  csrfToken: string
): Promise<AdminUserDetail> {
  return request(`/admin/users/${userId}`, jsonInit("PATCH", payload, csrfToken));
}

export interface AdminGroup {
  id: string;
  name: string;
  description: string | null;
  organization_id: string | null;
}

export interface AdminGroupDetail extends AdminGroup {
  role_ids: string[];
  member_ids: string[];
}

export function listGroups(): Promise<AdminGroup[]> {
  return request("/admin/groups");
}

export function getGroup(groupId: string): Promise<AdminGroupDetail> {
  return request(`/admin/groups/${groupId}`);
}

export function createGroup(
  payload: { name: string; description?: string | null; role_ids?: string[] },
  csrfToken: string
): Promise<AdminGroupDetail> {
  return request("/admin/groups", jsonInit("POST", payload, csrfToken));
}

export function updateGroup(
  groupId: string,
  payload: Partial<{ name: string; description: string | null; role_ids: string[] }>,
  csrfToken: string
): Promise<AdminGroupDetail> {
  return request(`/admin/groups/${groupId}`, jsonInit("PATCH", payload, csrfToken));
}

export interface AdminRole {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
}

export function listRoles(): Promise<AdminRole[]> {
  return request("/admin/roles");
}

// -- Organizations --------------------------------------------------------

export interface AdminOrganization {
  id: string;
  name: string;
  slug: string;
  description: string | null;
}

export function listOrganizations(): Promise<AdminOrganization[]> {
  return request("/organizations");
}

export function createOrganization(
  payload: { name: string; slug: string; description?: string | null },
  csrfToken: string
): Promise<AdminOrganization> {
  return request("/organizations", jsonInit("POST", payload, csrfToken));
}

export interface OrganizationMembership {
  id: string;
  user_id: string;
  organization_id: string;
  created_at: string;
}

export function listOrganizationMembers(orgId: string): Promise<OrganizationMembership[]> {
  return request(`/organizations/${orgId}/members`);
}

export function addOrganizationMember(
  orgId: string,
  userId: string,
  csrfToken: string
): Promise<OrganizationMembership> {
  return request(`/organizations/${orgId}/members`, jsonInit("POST", { user_id: userId }, csrfToken));
}

// -- Audit ------------------------------------------------------------

export interface AuditEvent {
  id: string;
  event_type: string;
  user_id: string | null;
  username: string | null;
  ip_address: string | null;
  user_agent: string | null;
  event_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditEventList {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export function listAuditEvents(params: {
  event_type?: string;
  username?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditEventList> {
  const search = new URLSearchParams();
  if (params.event_type) search.set("event_type", params.event_type);
  if (params.username) search.set("username", params.username);
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));
  return request(`/admin/audit-events?${search.toString()}`);
}

export function listAuditEventTypes(): Promise<{ event_types: string[] }> {
  return request("/admin/audit-events/event-types");
}

// -- Dashboard / Models -----------------------------------------------

export interface ComponentHealth {
  name: string;
  healthy: boolean;
  detail: string | null;
}

export interface DashboardStatus {
  components: ComponentHealth[];
  queue: { queued: number; running: number; failed: number };
  hardware: {
    cpu_count: number | null;
    total_ram_mb: number | null;
    cuda_available: boolean;
    gpu_device_name: string | null;
    total_vram_mb: number | null;
    free_vram_mb: number | null;
  };
  application_version: string;
}

export function getDashboard(): Promise<DashboardStatus> {
  return request("/admin/dashboard");
}

export interface ModelsOverview {
  speech: Record<string, unknown>;
  diarization: Record<string, unknown>;
  llm: {
    provider: string;
    model: string;
    model_revision: string | null;
    installed: boolean;
    device: string;
    structured_output: boolean;
    detail: string | null;
  };
}

export function getModelsOverview(): Promise<ModelsOverview> {
  return request("/admin/models");
}

// -- Jobs / Workers -----------------------------------------------------

export interface ProcessingJobSummary {
  id: string;
  conversation_id: string;
  job_type: string;
  status: string;
  progress: number;
  attempt: number;
  max_attempts: number;
  failure_class: string | null;
  error_code: string | null;
  error_message_safe: string | null;
  worker_id: string | null;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProcessingJobList {
  items: ProcessingJobSummary[];
  total: number;
  limit: number;
  offset: number;
}

export function listJobs(params: {
  status?: string;
  job_type?: string;
  limit?: number;
  offset?: number;
}): Promise<ProcessingJobList> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.job_type) search.set("job_type", params.job_type);
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));
  return request(`/admin/jobs?${search.toString()}`);
}

export function retryJob(jobId: string, csrfToken: string): Promise<ProcessingJobSummary> {
  return request(`/admin/jobs/${jobId}/retry`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export interface WorkerRoleStatus {
  role: string;
  job_types: string[];
  running_jobs: number;
  queued_jobs: number;
  active_worker_ids: string[];
  last_activity_at: string | null;
}

export function getWorkersOverview(): Promise<{ workers: WorkerRoleStatus[] }> {
  return request("/admin/workers");
}

// -- Storage / Retention --------------------------------------------------

export interface StorageUsage {
  media_storage_root: string;
  media_used_bytes: number;
  media_disk_total_bytes: number;
  media_disk_free_bytes: number;
  model_volume_root: string;
  model_volume_used_bytes: number;
  model_volume_disk_total_bytes: number;
  model_volume_disk_free_bytes: number;
}

export function getStorageUsage(): Promise<StorageUsage> {
  return request("/admin/storage");
}

export interface RetentionPolicy {
  id: string;
  name: string;
  retention_days: number | null;
  delete_source_media: boolean;
  delete_derived_media: boolean;
  delete_transcript: boolean;
  active: boolean;
  created_at: string;
}

export function listRetentionPolicies(): Promise<RetentionPolicy[]> {
  return request("/admin/retention-policies");
}

export function createRetentionPolicy(
  payload: {
    name: string;
    retention_days?: number | null;
    delete_source_media?: boolean;
    delete_derived_media?: boolean;
    delete_transcript?: boolean;
    active?: boolean;
  },
  csrfToken: string
): Promise<RetentionPolicy> {
  return request("/admin/retention-policies", jsonInit("POST", payload, csrfToken));
}

export function updateRetentionPolicy(
  policyId: string,
  payload: Partial<{
    name: string;
    retention_days: number | null;
    delete_source_media: boolean;
    delete_derived_media: boolean;
    delete_transcript: boolean;
    active: boolean;
  }>,
  csrfToken: string
): Promise<RetentionPolicy> {
  return request(`/admin/retention-policies/${policyId}`, jsonInit("PATCH", payload, csrfToken));
}

// -- Phase 11: Operations (Worker/GPU/Queue Metrics, Backup, Retention
// Cleanup, Model Storage) --------------------------------------------------

export interface WorkerMetrics {
  role: string;
  job_types: string[];
  running_jobs: number;
  queued_jobs: number;
  active_worker_ids: string[];
  last_activity_at: string | null;
  succeeded_last_1h: number;
  succeeded_last_24h: number;
  failed_last_24h: number;
  avg_duration_seconds_last_24h: number | null;
  sample_count_last_24h: number;
}

export interface GpuMetrics {
  cuda_available: boolean;
  device_name: string | null;
  total_vram_mb: number | null;
  free_vram_mb: number | null;
  utilization_percent: number | null;
}

export interface QueueMetrics {
  depth_by_job_type: { job_type: string; queued: number; running: number }[];
  throughput_hourly: { hour_start: string; succeeded: number; failed: number }[];
}

export interface OperationsMetrics {
  workers: WorkerMetrics[];
  gpu: GpuMetrics;
  queue: QueueMetrics;
}

export function getOperationsMetrics(): Promise<OperationsMetrics> {
  return request("/admin/operations/metrics");
}

export interface ModelStorageOverview {
  model_volume_root: string;
  total_bytes: number;
  models: { name: string; size_bytes: number }[];
}

export function getModelStorageOverview(): Promise<ModelStorageOverview> {
  return request("/admin/operations/model-storage");
}

export interface BackupRecord {
  id: string;
  status: string;
  database_dump_bytes: number | null;
  media_archive_bytes: number | null;
  media_file_count: number | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export function listBackups(): Promise<BackupRecord[]> {
  return request("/admin/operations/backups");
}

export function createBackup(csrfToken: string): Promise<BackupRecord> {
  return request("/admin/operations/backups", jsonInit("POST", {}, csrfToken));
}

export interface RetentionCleanupRun {
  id: string;
  dry_run: boolean;
  status: string;
  conversations_evaluated: number;
  items_deleted: number;
  bytes_freed: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface RetentionCleanupItem {
  id: string;
  run_id: string;
  conversation_id: string | null;
  retention_policy_id: string | null;
  action: string;
  media_asset_id: string | null;
  transcript_id: string | null;
  bytes_freed: number | null;
  segments_deleted: number | null;
  reason: string;
  created_at: string;
}

export function listRetentionCleanupRuns(): Promise<RetentionCleanupRun[]> {
  return request("/admin/operations/retention-cleanup/runs");
}

export function listRetentionCleanupItems(runId: string): Promise<RetentionCleanupItem[]> {
  return request(`/admin/operations/retention-cleanup/runs/${runId}/items`);
}

export function runRetentionCleanup(
  dryRun: boolean,
  csrfToken: string
): Promise<RetentionCleanupRun> {
  return request(
    "/admin/operations/retention-cleanup/run",
    jsonInit("POST", { dry_run: dryRun }, csrfToken)
  );
}

// -- About & Licenses -----------------------------------------------------

export interface AboutInfo {
  application_version: string;
  license_summary: Record<string, Record<string, number>>;
  third_party_notices_excerpt: string;
}

export function getAbout(): Promise<AboutInfo> {
  return request("/admin/about");
}

// -- Phase 10: Service Accounts & Webhooks ---------------------------------

export interface ServiceAccount {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  key_prefix: string;
  scopes: string[];
  is_active: boolean;
  owner_user_id: string | null;
  created_at: string;
  updated_at: string;
  last_rotated_at: string | null;
  last_used_at: string | null;
}

export interface ServiceAccountCreated extends ServiceAccount {
  api_key: string;
}

export function listServiceAccounts(): Promise<ServiceAccount[]> {
  return request("/admin/service-accounts");
}

export function listAvailableScopes(): Promise<{ scopes: string[] }> {
  return request("/admin/service-accounts/scopes");
}

export function createServiceAccount(
  payload: {
    name: string;
    description?: string | null;
    organization_id: string;
    scopes: string[];
    owner_user_id?: string | null;
  },
  csrfToken: string
): Promise<ServiceAccountCreated> {
  return request("/admin/service-accounts", jsonInit("POST", payload, csrfToken));
}

export function rotateServiceAccount(
  accountId: string,
  csrfToken: string
): Promise<ServiceAccountCreated> {
  return request(`/admin/service-accounts/${accountId}/rotate`, jsonInit("POST", {}, csrfToken));
}

export function revokeServiceAccount(accountId: string, csrfToken: string): Promise<ServiceAccount> {
  return request(`/admin/service-accounts/${accountId}/revoke`, jsonInit("POST", {}, csrfToken));
}

export interface Webhook {
  id: string;
  organization_id: string;
  name: string;
  target_url: string;
  event_types: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WebhookCreated extends Webhook {
  secret: string;
}

export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  attempt_number: number;
  status: string;
  response_status_code: number | null;
  error_message: string | null;
  created_at: string;
  delivered_at: string | null;
}

export function listWebhooks(): Promise<Webhook[]> {
  return request("/admin/webhooks");
}

export function listWebhookEventTypes(): Promise<{ event_types: string[] }> {
  return request("/admin/webhooks/event-types");
}

export function createWebhook(
  payload: { name: string; organization_id: string; target_url: string; event_types: string[] },
  csrfToken: string
): Promise<WebhookCreated> {
  return request("/admin/webhooks", jsonInit("POST", payload, csrfToken));
}

export function updateWebhook(
  webhookId: string,
  payload: Partial<{ name: string; target_url: string; event_types: string[]; is_active: boolean }>,
  csrfToken: string
): Promise<Webhook> {
  return request(`/admin/webhooks/${webhookId}`, jsonInit("PATCH", payload, csrfToken));
}

export function rotateWebhookSecret(webhookId: string, csrfToken: string): Promise<WebhookCreated> {
  return request(`/admin/webhooks/${webhookId}/rotate-secret`, jsonInit("POST", {}, csrfToken));
}

export function deleteWebhook(webhookId: string, csrfToken: string): Promise<void> {
  return request(`/admin/webhooks/${webhookId}`, { method: "DELETE", headers: { "X-CSRF-Token": csrfToken } });
}

export function listWebhookDeliveries(
  webhookId: string,
  params: { limit?: number; offset?: number } = {}
): Promise<{ items: WebhookDelivery[]; total: number }> {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  const qs = query.toString();
  return request(`/admin/webhooks/${webhookId}/deliveries${qs ? `?${qs}` : ""}`);
}
