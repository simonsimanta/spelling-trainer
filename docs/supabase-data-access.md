# Supabase Data Access Model

## Intended clients and roles

| Client | Connection | Database role | Required access |
| --- | --- | --- | --- |
| React frontend | FastAPI HTTP endpoints only | None | No direct Supabase Data API access |
| FastAPI backend | SQLAlchemy through `DATABASE_URL` and the Supabase session pooler | `postgres` | Full application-table access |
| Alembic | Same trusted `DATABASE_URL` | `postgres` | Schema migration access |
| Supabase Dashboard and operator tooling | Supabase management connection | Platform-managed operator role | Administrative access |
| Supabase Data API | Publishable/legacy anon key or user JWT | `anon`, `authenticated` | Denied |
| Server-side Supabase Data API | Secret/service-role key | `service_role` | Denied because this app does not use it |

The browser does not import `supabase-js`, does not contain a publishable key, and does not query PostgREST or GraphQL. All learner data flows through FastAPI. The backend connection maps to the `postgres` table owner and has `BYPASSRLS`, so RLS protects the Data API without changing existing SQLAlchemy workflows.

## Security boundary

Supabase Data API authorization has two independent layers:

1. PostgreSQL grants decide whether a Data API role can reach an object.
2. Row Level Security policies decide which rows that role may read or change.

Migration `20260801_0010` applies both layers to every application table in the exposed `public` schema:

- RLS is enabled.
- A restrictive `deny_browser_data_api` policy explicitly rejects `anon` and `authenticated` reads and writes.
- Existing table, sequence, function, and schema privileges are revoked from `anon`, `authenticated`, and `service_role`.
- Default privileges for future objects created by `postgres` are revoked from those Data API roles.
- Function execution is also revoked from `PUBLIC` by default.

No allow policy is present because browser-side database access is not part of this product. If a future feature introduces direct Supabase access, it must add narrowly scoped grants and ownership-based RLS policies in a new reviewed migration.

Tables in `legacy_mylife` are preserved outside the exposed Data API schema and are not changed by this migration.

## Relational indexes

PostgreSQL does not automatically index foreign-key columns. The migration adds indexes for the five public foreign keys reported by the Supabase performance advisor:

- `activity_events.word_id`
- `spelling_attempts.word_id`
- `spelling_confusion_group_words.word_id`
- `spelling_suggestions.word_id`
- `spelling_word_patterns.pattern_id`

These indexes speed up joins and the parent-row checks required by cascades and `SET NULL` actions.

## Verification and rollback

Before deployment:

```bash
python -m pytest tests/backend/test_database_hardening_migration.py -q
python -m pytest -q
python -m alembic upgrade head
```

After deployment, verify that:

- an anonymous request to `/rest/v1/spelling_attempts` receives `401` or `403`;
- `/readiness`, `/dashboard`, and a write-based spelling workflow still succeed through FastAPI;
- `alembic_version` is `20260801_0010`;
- Supabase security advisor no longer reports public tables without RLS;
- the five public unindexed-foreign-key findings are gone.

### Deployment verification: 2026-08-01

- Alembic reports `20260801_0010` on the live Supabase project.
- All 20 `public` tables have RLS enabled and the `deny_browser_data_api` policy.
- A publishable-key request to `spelling_attempts` changed from HTTP `200` before the migration to HTTP `401` after it.
- Catalog privilege checks confirm `anon`, `authenticated`, and `service_role` have no `SELECT` or `INSERT` privilege on `spelling_attempts`.
- FastAPI `/readiness` and `/dashboard` return HTTP `200`, and creating a Practice session succeeds through the backend pooler connection.
- The Supabase security advisor returns no findings.
- The performance advisor no longer reports any unindexed foreign keys in `public`.
- The PostgreSQL downgrade function executes successfully inside a live transaction; rolling that transaction back leaves revision `20260801_0010` and the Data API denial intact.

Remaining performance notices are intentional for this ticket:

- `legacy_mylife.habits.category_id` remains an unindexed foreign key because the archived legacy schema is outside the spelling product boundary.
- Existing primary-key helper indexes and the new low-traffic foreign-key indexes may be reported as unused. Usage statistics immediately after creation are not evidence that a referential-integrity index is unnecessary.

The tested emergency rollback is:

```bash
python -m alembic downgrade 20260730_0009
```

Rollback restores the previous Data API grants and disables RLS, so it reopens the original vulnerability. Use it only to restore service while diagnosing an unexpected backend compatibility problem, then reapply the hardening migration.
