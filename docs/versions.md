# Version Matrix & Upgrade Log

> Governing rule (CLAUDE.md): **mutual compatibility first, then newest.** All versions are
> pinned in lockfiles; no open ranges (`^`/`~`) for critical packages. Upgrades happen as one
> tested wave, between phases only. Every upgrade is recorded here with its rationale.

## Approved matrix (from CLAUDE.md v1.1 — verified & pinned at project start)

### Runtime

| Package | Target | Notes |
|---|---|---|
| Node.js | 22 LTS | Next.js 16 requires Node 20+. |
| Python | 3.12 | Stable across the full dependency chain. |

### Frontend

| Package | Target |
|---|---|
| Next.js | 16.x (App Router, Turbopack default) |
| React | 19.x |
| TypeScript | 5.x (strict) |
| Tailwind CSS | 4.x |
| shadcn/ui | latest compatible with Tailwind 4 |
| Zustand | 5.x |
| TanStack Query | 5.x |
| React Hook Form + Zod | latest stable |
| Recharts | latest stable |

### Desktop

| Package | Target |
|---|---|
| Electron | latest stable line (>=33), pinned after verification |
| electron-builder | compatible with the pinned Electron line |

### Backend

| Package | Target |
|---|---|
| FastAPI | >=0.115 (Pydantic v2 compatible) |
| SQLAlchemy | 2.0 (async) |
| Pydantic | v2 |
| Celery | 5.x |
| WeasyPrint | latest stable (A4/A5 reports only) |
| python-barcode + GS1 DataMatrix parser | latest stable |

### Database / infra

| Package | Target |
|---|---|
| PostgreSQL | 17 (local Docker; must match the Supabase project major) |
| Supabase CLI | latest stable |
| Redis | 7.x |

Migrations: SQL via Supabase CLI only (`supabase/migrations/`). No Alembic — SQLAlchemy models
mirror the schema, they are not its source.

## Toolchain pins provisionally applied in P0-M1 (root devDependencies)

These are the dev toolchain pins committed in `package.json`. Per the version policy, the first
`pnpm install` on a networked machine is the **verification gate**: it resolves the lockfile and,
where a newer compatible stable exists, the pin is bumped as one wave and recorded below.

| Package | Provisional pin |
|---|---|
| typescript | 5.7.2 |
| turbo | 2.3.3 |
| eslint / @eslint/js | 9.17.0 |
| typescript-eslint | 8.18.1 |
| prettier | 3.4.2 |
| husky | 9.1.7 |
| lint-staged | 15.2.11 |
| @commitlint/cli | 19.6.1 |
| @commitlint/config-conventional | 19.6.0 |

## Environment reconciliation (open — tracked under decision D0)

The current authoring sandbox differs from the pinned targets and must be reconciled where Phase 0
is actually built/verified:

| Item | Target | Sandbox | Action |
|---|---|---|---|
| Node.js | 22 LTS | 24.x | CI pins Node 22; `.nvmrc` = 22. |
| Python | 3.12 | 3.9 | Provision 3.12 on the build/verify machine. |
| Docker + Compose | required | absent | DB-dependent steps run on a Docker-enabled machine/CI. |
| PostgreSQL / Redis | 17 / 7 | absent | Provided via Docker Compose (P0-M2). |
| Supabase CLI | latest | absent | Installed on the build/verify machine (P0-M3). |
| Package registries | reachable | egress restricted | Allowlist required before `pnpm install`. |

## Upgrade log

- **2026-07 — Initial matrix (v1.1).** Adopted the CLAUDE.md v1.1 matrix as the project baseline.
  Provisional toolchain pins committed in P0-M1; to be validated at the first networked
  `pnpm install`.
