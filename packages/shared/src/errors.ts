/**
 * Error-code registry (CLAUDE.md: packages/shared/errors.ts).
 * Append-only — codes are added, never modified.
 *
 * The API returns these stable codes; the UI translates them per locale
 * (t(`errors.${code}`)). Kept identical to apps/api/.../errors.py.
 */

export const ERROR_CODES = {
  STOCK_INSUFFICIENT: 'E-STK-001', // المخزون غير كافٍ
  BATCH_EXPIRED: 'E-STK-002', // الدفعة منتهية/محجورة
  VALIDATION_FAILED: 'E-VAL-001',
  UNAUTHORIZED: 'E-AUTH-001',
  PERMISSION_DENIED: 'E-AUTH-002',
  ACCOUNT_LOCKED: 'E-AUTH-003', // قفل بعد محاولات فاشلة متكررة
  CSRF_FAILED: 'E-AUTH-004',
  RATE_LIMITED: 'E-AUTH-005',
  USERNAME_TAKEN: 'E-USR-001',
  BARCODE_TAKEN: 'E-CAT-001',
  ERECEIPT_REJECTED: 'E-ETA-001',
  TT_REPORT_FAILED: 'E-TT-001',
  SYNC_CONFLICT: 'E-SYN-001',
  PRINTER_NOT_CONFIGURED: 'E-PRN-001', // لا توجد طابعة مهيأة على الجهاز
  PRINTER_UNREACHABLE: 'E-PRN-002', // تعذر الوصول لطابعة الإيصالات
  PAPER_NOT_THERMAL: 'E-PRN-003', // مقاس الورق ليس 80mm حرارياً
  SESSION_ALREADY_OPEN: 'E-CSH-001', // لدى الكاشير جلسة مفتوحة بالفعل
  SESSION_NOT_OPEN: 'E-CSH-002', // الجلسة ليست مفتوحة
  UNEXPECTED: 'E-SYS-001',
} as const;

export type ErrorCode = (typeof ERROR_CODES)[keyof typeof ERROR_CODES];

/** Unified API response shape (CLAUDE.md). */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string; // from the registry — the UI translates
    message: string; // request-language fallback text
    details?: unknown; // debugging only — never shown to the user
  };
  meta?: {
    page: number;
    total: number;
    per_page: number;
  };
}
