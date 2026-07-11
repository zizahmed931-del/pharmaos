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
