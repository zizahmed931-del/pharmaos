# PharmaOS

Hybrid (offline-first + cloud) pharmacy management system. Production-grade, multi-country / multi-currency, with **Egypt (EGP)** as the primary market. Built by a single developer.

> The authoritative project specifications are **`CLAUDE.md`** and **`pharmaos.md`**.
> On any conflict, **`CLAUDE.md` wins**. This README is a convenience entry point, not a source of truth.

## Monorepo layout

```
PharmaOS/
├── apps/
│   ├── desktop/   # Electron + Next.js (local device app)
│   ├── web/       # Next.js web dashboard (cloud)
│   └── api/       # FastAPI backend (local + cloud)
├── packages/
│   ├── ui/        # Shared UI components (shadcn/ui + Tailwind 4, RTL-first)
│   ├── db/        # Migration helpers & schema utilities
│   └── shared/    # Shared types, permission matrix, error-code registry
├── supabase/      # Migrations only — do NOT edit directly
└── docs/          # versions.md and project docs
```

## Toolchain (targets)

| Tool | Target |
|---|---|
| Node.js | 22 LTS |
| pnpm | 10.x |
| Python | 3.12 |
| PostgreSQL | 17 (Docker) |
| Redis | 7 (Docker) |

Exact pins live in `docs/versions.md` and in the lockfiles. See the version policy in `CLAUDE.md`.

## Local development

```bash
pnpm install          # install JS/TS toolchain and workspaces
# infrastructure (PostgreSQL 17 + Redis 7) — added in P0-M2
# docker compose up -d
```

Root scripts: `pnpm build`, `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm format`.

## Status

Under active Phase 0 (Foundations) implementation. See `docs/versions.md` and the project
context for milestone progress.
