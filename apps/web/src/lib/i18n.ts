/**
 * i18n (CLAUDE.md): defaultLocale 'ar', locales ['ar','en'], RTL for Arabic.
 * API errors arrive as stable codes and are translated here —
 * t(`errors.${code}`) — never hardcoded in the API layer.
 */

export const i18nConfig = {
  defaultLocale: 'ar',
  locales: ['ar', 'en'],
  direction: { ar: 'rtl', en: 'ltr' },
} as const;

export type Locale = (typeof i18nConfig.locales)[number];

const dictionaries: Record<Locale, Record<string, string>> = {
  ar: {
    'app.name': 'PharmaOS',
    'app.tagline': 'نظام إدارة الصيدلية',
    'login.title': 'تسجيل الدخول',
    'login.username': 'اسم المستخدم',
    'login.password': 'كلمة المرور',
    'login.submit': 'دخول',
    'login.submitting': 'جارٍ الدخول…',
    'errors.E-AUTH-001': 'بيانات الدخول غير صحيحة',
    'errors.E-AUTH-002': 'ليست لديك صلاحية لهذا الإجراء',
    'errors.E-AUTH-003': 'تم قفل الحساب مؤقتاً بعد محاولات متكررة — حاول بعد 15 دقيقة',
    'errors.E-AUTH-004': 'فشل التحقق الأمني — أعد تحميل الصفحة',
    'errors.E-AUTH-005': 'محاولات كثيرة — انتظر دقيقة ثم أعد المحاولة',
    'errors.E-VAL-001': 'بيانات غير صالحة — راجع الحقول',
    'errors.E-SYS-001': 'خطأ غير متوقع — حاول مجدداً',
    'errors.unexpected': 'خطأ غير متوقع — حاول مجدداً',
    'validation.username_required': 'اسم المستخدم مطلوب',
    'validation.password_required': 'كلمة المرور مطلوبة',
  },
  en: {
    'app.name': 'PharmaOS',
    'app.tagline': 'Pharmacy Management System',
    'login.title': 'Sign in',
    'login.username': 'Username',
    'login.password': 'Password',
    'login.submit': 'Sign in',
    'login.submitting': 'Signing in…',
    'errors.E-AUTH-001': 'Invalid credentials',
    'errors.E-AUTH-002': 'You do not have permission for this action',
    'errors.E-AUTH-003': 'Account temporarily locked — try again in 15 minutes',
    'errors.E-AUTH-004': 'Security check failed — reload the page',
    'errors.E-AUTH-005': 'Too many attempts — wait a minute and retry',
    'errors.E-VAL-001': 'Invalid data — review the fields',
    'errors.E-SYS-001': 'Unexpected error — please retry',
    'errors.unexpected': 'Unexpected error — please retry',
    'validation.username_required': 'Username is required',
    'validation.password_required': 'Password is required',
  },
};

export function t(key: string, locale: Locale = i18nConfig.defaultLocale): string {
  return dictionaries[locale][key] ?? dictionaries[i18nConfig.defaultLocale][key] ?? key;
}
