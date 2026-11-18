# ADR 0002: Tenant isolation with Postgres row-level security

**Status:** accepted

## Context
Every query needs a tenant filter. Filters written in application code fail open: one forgotten `WHERE`
leaks another business's customers.

## Decision
Every tenant table has `FORCE ROW LEVEL SECURITY` and a policy
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid` for both reads and writes. The
application connects as `oryn_app` (no `BYPASSRLS`) and sets `app.tenant_id` per transaction with
`set_config(..., is_local => true)`. Migrations and seeding use `oryn_owner`. Two cross-tenant lookups
are narrow `SECURITY DEFINER` functions.

## Consequences
- A missing filter returns no rows instead of other tenants' rows; inserting into another tenant fails.
- A schema test asserts every table with a `tenant_id` column has the policy.
- `NULLIF` is required because pooled connections reset the setting to `''`, not `NULL`.
- Background work must always establish tenant context explicitly (activities take `tenant_id` as input).
