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

// ---- Catalog editor: packaging levels & barcodes (P1-M7 UI; API since M5) ----

export interface Unit {
  id: string;
  name_ar: string;
  name_en: string | null;
}

export interface PackagingLevel {
  id: string;
  level: number;
  unit_id: string;
  name_ar: string;
  qty_in_parent: string | null;
  is_sellable: boolean;
  selling_price: string;
  is_default_sale: boolean;
  price_source: string;
}

export interface Barcode {
  id: string;
  barcode: string;
  barcode_type: string;
  packaging_id: string | null;
  is_primary: boolean;
}

export interface MedicationDetail {
  id: string;
  trade_name: string;
  trade_name_ar: string | null;
  scientific_name: string | null;
  manufacturer: string | null;
  drug_class: string | null;
  route: string | null;
  requires_prescription: boolean;
  controlled_substance: boolean;
  storage_conditions: string | null;
  eda_registration_no: string | null;
  gtin: string | null;
  is_active: boolean;
  packaging: PackagingLevel[];
  barcodes: Barcode[];
}

/** One packaging level as submitted by the editor (server validates the set). */
export interface PackagingLevelInput {
  level: number;
  unit_id: string;
  name_ar: string;
  qty_in_parent: string | null;
  selling_price: string;
  is_sellable: boolean;
  is_default_sale: boolean;
}

export function listUnits() {
  return apiFetch<Unit[]>('/api/v1/catalog/units');
}

export function getMedication(id: string) {
  return apiFetch<MedicationDetail>(`/api/v1/medications/${id}`);
}

export function updateMedication(id: string, values: Record<string, unknown>) {
  return apiFetch<MedicationDetail>(`/api/v1/medications/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(values),
  });
}

export function deleteMedication(id: string) {
  return apiFetch<{ deleted: boolean }>(`/api/v1/medications/${id}`, { method: 'DELETE' });
}

export function putPackaging(id: string, levels: PackagingLevelInput[], priceSource = 'manual') {
  return apiFetch<PackagingLevel[]>(`/api/v1/medications/${id}/packaging`, {
    method: 'PUT',
    body: JSON.stringify({ levels, price_source: priceSource }),
  });
}

export function addBarcode(
  id: string,
  input: {
    barcode: string;
    barcode_type?: string;
    packaging_id?: string | null;
    is_primary?: boolean;
  },
) {
  return apiFetch<Barcode>(`/api/v1/medications/${id}/barcodes`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function deleteBarcode(id: string, barcodeId: string) {
  return apiFetch<{ deleted: boolean }>(`/api/v1/medications/${id}/barcodes/${barcodeId}`, {
    method: 'DELETE',
  });
}

// ---- Inventory: stock on hand, batches, receiving, adjustments (P1-M7) ----

export interface InventoryBranch {
  id: string;
  name: string;
  currency_code: string;
}

export interface InventoryRow {
  medication_id: string;
  trade_name: string;
  trade_name_ar: string | null;
  cached_quantity: string;
  min_stock_level: string | null;
  reorder_point: string | null;
  shelf_location: string | null;
  low_stock: boolean;
}

export interface Batch {
  id: string;
  branch_id: string;
  medication_id: string;
  trade_name?: string;
  trade_name_ar?: string | null;
  batch_number: string;
  expiry_date: string;
  quantity: string;
  purchase_price: string;
  supplier_id: string | null;
  status: string;
  received_at: string;
}

export interface Supplier {
  id: string;
  name: string;
}

export interface Gs1Parse {
  gtin: string | null;
  expiry_date: string | null;
  batch_number: string | null;
  serial_number: string | null;
  medication: {
    id: string;
    trade_name: string;
    trade_name_ar: string | null;
    gtin: string | null;
  } | null;
}

export interface ReceiveInput {
  branch_id: string;
  medication_id: string;
  batch_number: string;
  expiry_date: string;
  quantity: string;
  purchase_price: string;
  supplier_id?: string | null;
}

export function listInventoryBranches() {
  return apiFetch<InventoryBranch[]>('/api/v1/inventory/branches');
}

export function listInventory(
  branchId: string,
  opts: { search?: string; lowStock?: boolean } = {},
) {
  const params = new URLSearchParams({ branch_id: branchId, limit: '100' });
  if (opts.search) params.set('search', opts.search);
  if (opts.lowStock) params.set('low_stock', 'true');
  return apiFetch<InventoryRow[]>(`/api/v1/inventory?${params.toString()}`);
}

export function listBatches(
  branchId: string,
  opts: { medicationId?: string; status?: string } = {},
) {
  const params = new URLSearchParams({ branch_id: branchId, limit: '100' });
  if (opts.medicationId) params.set('medication_id', opts.medicationId);
  if (opts.status) params.set('status', opts.status);
  return apiFetch<Batch[]>(`/api/v1/inventory/batches?${params.toString()}`);
}

export function parseGs1(code: string) {
  return apiFetch<Gs1Parse>(`/api/v1/catalog/parse-gs1?code=${encodeURIComponent(code)}`);
}

export function receiveStock(input: ReceiveInput) {
  return apiFetch<Batch>('/api/v1/inventory/receive', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function adjustBatch(batchId: string, quantityDelta: string, reason: string) {
  return apiFetch<Batch>(`/api/v1/inventory/batches/${batchId}/adjust`, {
    method: 'POST',
    body: JSON.stringify({ quantity_delta: quantityDelta, reason }),
  });
}

export function setBatchStatus(batchId: string, status: string, reason = '') {
  return apiFetch<Batch>(`/api/v1/inventory/batches/${batchId}/status`, {
    method: 'POST',
    body: JSON.stringify({ status, reason }),
  });
}

export function listSuppliers() {
  return apiFetch<Supplier[]>('/api/v1/inventory/suppliers');
}

export function createSupplier(name: string) {
  return apiFetch<Supplier>('/api/v1/inventory/suppliers', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export interface DriftReport {
  drift: Array<{ medication_id: string; cached: string; truth: string }>;
  ok: boolean;
}

export function checkDrift(branchId: string) {
  return apiFetch<DriftReport>(`/api/v1/inventory/drift?branch_id=${branchId}`);
}

export function rebuildCache(branchId: string) {
  return apiFetch<{ rows: number }>('/api/v1/inventory/rebuild', {
    method: 'POST',
    body: JSON.stringify({ branch_id: branchId }),
  });
}

export interface MedOption {
  id: string;
  trade_name: string;
  trade_name_ar: string | null;
}

/** Catalog search for the receiving picker (a batch can be received for any med). */
export function searchMedications(term: string) {
  return apiFetch<MedOption[]>(`/api/v1/medications?limit=10&search=${encodeURIComponent(term)}`);
}
