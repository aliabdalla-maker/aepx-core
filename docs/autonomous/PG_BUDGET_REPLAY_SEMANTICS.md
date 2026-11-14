# PostgreSQL reservation replay semantics

The `aepx_budget.reserve` function returns `reserved` only for a newly created reservation. A matching replay of an active reservation returns `already_reserved`. A matching replay after settlement now returns `already_settled`, not `already_reserved`. A conflicting replay remains an error.

**Dispatch policy:** neither `already_reserved` nor `already_settled` grants permission for a new provider call. Even `reserved` must be paired with durable dispatch fencing and an immutable provider idempotency key. The function is not yet wired to provider execution, and the SQL fixture must still be executed against a disposable local PostgreSQL database under a non-BYPASSRLS role. Never interpret the change as protection from duplicate provider charges on its own.

The migration is still staging-only; no production database was changed.
