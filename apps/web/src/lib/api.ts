/**
 * Typed API client — unified ApiResponse envelope (packages/shared).
 * Cookies are first-party via the Next.js rewrite proxy to 127.0.0.1.
 * Mutating requests carry the CSRF header (double-submit pattern).
 */

import type { ApiResponse } from '@pharmaos/shared';

export class ApiRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

function readCsrfCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)pharmaos_csrf=([^;]+)/);
  return match?.[1] ?? null;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? 'GET';
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type') && init?.body) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = readCsrfCookie();
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }

  const response = await fetch(path, { ...init, headers, credentials: 'include' });
  const body = (await response.json()) as ApiResponse<T>;
  if (!body.success || body.data === undefined) {
    throw new ApiRequestError(body.error?.code ?? 'E-SYS-001', body.error?.message ?? '');
  }
  return body.data;
}

export interface SessionUser {
  id: string;
  username: string;
  full_name: string;
  role: string | null;
}

export function login(username: string, password: string) {
  return apiFetch<{ user: SessionUser; csrf_token: string }>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function fetchMe() {
  return apiFetch<{ user: SessionUser }>('/api/v1/auth/me');
}

export function logout() {
  return apiFetch<{ logged_out: boolean }>('/api/v1/auth/logout', { method: 'POST' });
}

// ---- User & role management (P1-M3; super_admin only) ----

export interface ManagedUser {
  id: string;
  username: string;
  full_name: string;
  role: string | null;
  phone: string | null;
  is_active: boolean;
  created_at: string;
}

export interface CreateUserInput {
  username: string;
  full_name: string;
  password: string;
  role_code: string;
  phone?: string | null;
}

export function listUsers() {
  return apiFetch<ManagedUser[]>('/api/v1/users?limit=100');
}

export function createUser(input: CreateUserInput) {
  return apiFetch<ManagedUser>('/api/v1/users', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function changeUserRole(id: string, roleCode: string) {
  return apiFetch<ManagedUser>(`/api/v1/users/${id}/role`, {
    method: 'POST',
    body: JSON.stringify({ role_code: roleCode }),
  });
}

export function setUserActive(id: string, active: boolean) {
  return apiFetch<ManagedUser>(`/api/v1/users/${id}/active`, {
    method: 'POST',
    body: JSON.stringify({ active }),
  });
}

export function resetUserPassword(id: string, newPassword: string) {
  return apiFetch<{ reset: boolean }>(`/api/v1/users/${id}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  });
}

// ---- Branch & settings (P1-M4) ----

export interface BranchInfo {
  id: string;
  name: string;
  country_code: string;
  currency_code: string;
  is_active: boolean;
}

export interface BranchSettings {
  id: string;
  branch_id: string;
  pharmacy_name: string;
  pharmacy_logo: string | null;
  license_number: string | null;
  address: string | null;
  phone: string | null;
  tax_registration_no: string | null;
  return_policy: string | null;
  thank_you_message: string | null;
  paper_size: '80mm' | 'A4' | 'A5';
  show_pharmacist_signature: boolean;
  show_qr_code: boolean;
  max_discount_percent: string;
}

export function listBranches() {
  return apiFetch<BranchInfo[]>('/api/v1/branches');
}

export function getSettings(branchId: string) {
  return apiFetch<BranchSettings | null>(`/api/v1/branches/${branchId}/settings`);
}

export function putSettings(branchId: string, values: Record<string, unknown>) {
  return apiFetch<BranchSettings>(`/api/v1/branches/${branchId}/settings`, {
    method: 'PUT',
    body: JSON.stringify(values),
  });
}

export function updateBranch(branchId: string, values: Record<string, unknown>) {
  return apiFetch<BranchInfo>(`/api/v1/branches/${branchId}`, {
    method: 'PATCH',
    body: JSON.stringify(values),
  });
}
