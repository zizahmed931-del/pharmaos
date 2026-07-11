import type { Metadata } from 'next';
import { Cairo, Inter } from 'next/font/google';

import { Providers } from './providers';
import './globals.css';

// Arabic UI font + Inter for numbers (CLAUDE.md design system).
const cairo = Cairo({ subsets: ['arabic', 'latin'], variable: '--font-cairo' });
const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

export const metadata: Metadata = {
  title: 'PharmaOS — نظام إدارة الصيدلية',
  description: 'نظام إدارة صيدلية يعمل offline مع مزامنة سحابية',
};

/**
 * Root layout — FULL RTL (CLAUDE.md UX rules: no mixed RTL/LTR in a page).
 * Default locale is Arabic; the i18n config also supports 'en'.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl" className={`${cairo.variable} ${inter.variable}`}>
      <body className="min-h-screen bg-surface antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
