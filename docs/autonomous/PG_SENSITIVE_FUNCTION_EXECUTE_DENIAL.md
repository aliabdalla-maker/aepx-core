# Sensitive function execution: untrusted runtime role audit

The read-only `tests/sql/aepx_runtime_function_grant_audit.sql` now fails if the current **untrusted** runtime role has EXECUTE on any discovered sensitive iteration or budget function. Previously it only printed that privilege. The audit also rejects fewer than four inspected sensitive functions.

This is a **strict role-separation policy**. It must be run as an untrusted API/worker identity, not as the future independently authenticated controller. Existing SECURITY INVOKER functions need appropriate trusted controller grants and redesigned transaction boundaries before runtime callers can be denied direct EXECUTE without breaking legitimate operations. No grants are changed by this audit, and it does not authenticate tenant context, reviewer approval or DB transaction completion. Static tests only; PostgreSQL runtime and CI remain unverified.
