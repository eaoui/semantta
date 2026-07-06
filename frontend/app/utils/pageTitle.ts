// utils/pageTitle.ts
// Derives a human‑readable page name from an admin route path.

export function getAdminPageTitle(path: string): string {
  const segments = path
    .replace(/^\/admin\/?/, '')
    .split('/')
    .filter(Boolean)

  if (segments.length === 0) return 'Dashboard'

  const last = segments[segments.length - 1]!
  return last
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}