/**
 * Dashboard navigation — each item declares the permission required to see it.
 * The sidebar filters items with hasPermission (packages/shared matrix), so a
 * cashier never sees Reports/Settings, etc. Backend guards remain authoritative;
 * this is UX only.
 *
 * Routes for sections not yet built (Phase 1 milestones M3+) are included but
 * flagged `ready: false` so the shell can render them as disabled "coming soon"
 * entries — the information architecture is stable from the start.
 */

export interface NavItem {
  href: string;
  labelKey: string;
  permission: string;
  ready: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: '/', labelKey: 'nav.dashboard', permission: 'sales.view', ready: true },
  { href: '/pos', labelKey: 'nav.pos', permission: 'sales.create', ready: false },
  { href: '/catalog', labelKey: 'nav.catalog', permission: 'inventory.view', ready: false },
  { href: '/inventory', labelKey: 'nav.inventory', permission: 'inventory.view', ready: false },
  { href: '/purchases', labelKey: 'nav.purchases', permission: 'purchases.view', ready: false },
  { href: '/customers', labelKey: 'nav.customers', permission: 'customers.view', ready: false },
  { href: '/cashier', labelKey: 'nav.cashier', permission: 'cashier.open_session', ready: false },
  { href: '/reports', labelKey: 'nav.reports', permission: 'reports.sales', ready: false },
  { href: '/users', labelKey: 'nav.users', permission: 'settings.users', ready: true },
  { href: '/settings', labelKey: 'nav.settings', permission: 'settings.view', ready: false },
];
