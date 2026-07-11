import { redirect } from 'next/navigation';

/** Phase 0 shell: the application entry is the login screen. */
export default function HomePage() {
  redirect('/login');
}
