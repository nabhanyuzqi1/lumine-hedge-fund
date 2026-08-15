// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Admin API client per Phase 9 API contract.
 *
 * Handles:
 * - Dynamic API key lifecycle (list/create/revoke)
 * - Kill-switch arm/disarm with audit trail (reason + tier)
 *
 * Maps to backend routers/admin.py (mounted at /api/v1/admin/*).
 */

import { api } from '../core';
import type { AdminKey, CreatedAdminKey, KillSwitchStatus, KillSwitchTier } from '../types';

export interface CreateKeyRequest {
  key_id: string;
  name?: string;
  scopes: string[];
}

export interface SetKillSwitchRequest {
  armed: boolean;
  reason: string;
  tier?: KillSwitchTier;
}

/**
 * List all dynamic API keys (excluding the bootstrap key).
 */
export async function listApiKeys(): Promise<AdminKey[]> {
  const result = await api.get<{ data: AdminKey[] }>(`/api/admin/keys`);
  if (result.error) throw result.error;
  return result.data?.data ?? [];
}

/**
 * Create a new dynamic API key. The secret is returned exactly once.
 */
export async function createApiKey(request: CreateKeyRequest): Promise<CreatedAdminKey> {
  const result = await api.post<{ data: CreatedAdminKey }>('/api/admin/keys', request);
  if (result.error) throw result.error;
  return result.data!.data;
}

/**
 * Revoke a dynamic API key (bootstrap key cannot be revoked via API).
 */
export async function revokeApiKey(keyId: string): Promise<AdminKey> {
  const result = await api.delete<{ data: AdminKey }>(`/api/admin/keys/${encodeURIComponent(keyId)}`);
  if (result.error) throw result.error;
  return result.data!.data;
}

/**
 * Fetch the current kill-switch state.
 */
export async function getKillSwitchStatus(): Promise<KillSwitchStatus> {
  const result = await api.get<{ data: KillSwitchStatus }>(`/api/admin/kill-switch`);
  if (result.error) throw result.error;
  return result.data!.data;
}

/**
 * Arm or disarm the kill switch (auditable action with reason + tier).
 */
export async function setKillSwitch(request: SetKillSwitchRequest): Promise<KillSwitchStatus> {
  const result = await api.post<{ data: KillSwitchStatus }>('/api/admin/kill-switch', request);
  if (result.error) throw result.error;
  return result.data!.data;
}
