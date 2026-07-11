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
    // Shell / navigation
    'nav.dashboard': 'الرئيسية',
    'nav.pos': 'نقطة البيع',
    'nav.inventory': 'المخزون',
    'nav.catalog': 'كتالوج الأدوية',
    'nav.purchases': 'المشتريات',
    'nav.customers': 'العملاء',
    'nav.reports': 'التقارير',
    'nav.cashier': 'جلسات الكاشير',
    'nav.users': 'المستخدمون',
    'nav.settings': 'الإعدادات',
    'shell.logout': 'تسجيل الخروج',
    'shell.online': 'متصل',
    'shell.offline': 'غير متصل — يعمل محلياً',
    'shell.loading': 'جارٍ التحميل…',
    'dashboard.welcome': 'مرحباً',
    'dashboard.role': 'الدور',
    'dashboard.quick_actions': 'إجراءات سريعة',
    'dashboard.coming_soon': 'قيد الإنشاء في المراحل التالية',
    'role.super_admin': 'مالك النظام',
    'role.branch_manager': 'مدير الفرع',
    'role.pharmacist': 'صيدلاني',
    'role.cashier': 'كاشير',
    'role.data_entry': 'مدخل بيانات',
    'role.viewer': 'مشاهدة فقط',
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
    // Shell / navigation
    'nav.dashboard': 'Dashboard',
    'nav.pos': 'Point of Sale',
    'nav.inventory': 'Inventory',
    'nav.catalog': 'Medications',
    'nav.purchases': 'Purchases',
    'nav.customers': 'Customers',
    'nav.reports': 'Reports',
    'nav.cashier': 'Cash sessions',
    'nav.users': 'Users',
    'nav.settings': 'Settings',
    'shell.logout': 'Sign out',
    'shell.online': 'Online',
    'shell.offline': 'Offline — working locally',
    'shell.loading': 'Loading…',
    'dashboard.welcome': 'Welcome',
    'dashboard.role': 'Role',
    'dashboard.quick_actions': 'Quick actions',
    'dashboard.coming_soon': 'Coming in later phases',
    'role.super_admin': 'System owner',
    'role.branch_manager': 'Branch manager',
    'role.pharmacist': 'Pharmacist',
    'role.cashier': 'Cashier',
    'role.data_entry': 'Data entry',
    'role.viewer': 'Viewer',
  },
};

export function t(key: string, locale: Locale = i18nConfig.defaultLocale): string {
  return dictionaries[locale][key] ?? dictionaries[i18nConfig.defaultLocale][key] ?? key;
}
