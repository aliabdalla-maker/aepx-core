# PostgreSQL fenced iteration state (foundation)

The staging-only migration `platform/saas-ide/backend/sql/aepx_iteration_fenced.sql` defines tenant-scoped work items, one incomplete iteration per tenant, a lease claim with monotonic fencing token, and a row-locked six-stage transition function. An expired lease may be replaced with a higher fence; a stale owner/fence or expired lease cannot advance the record. Completion clears the lease.

**Not ready for production.** The SQL is not applied or executed in CI. The custom `app.tenant_id` setting is **not authenticated** by PostgreSQL and must be bound to a trusted session authority. This schema does not verify signatures, evidence bytes, test results or reviewer approvals; the `completed` stage currently accepts a string reference and must be gated by trusted approval and evidence checks before any real workflow. It does not implement provider dispatch, billing, a lease heartbeat, crash-injection tests or external worker fencing.

Next: add disposable PostgreSQL acceptance tests with a non-owner non-BYPASSRLS role; exercise two concurrent connections and lease expiry; build trusted approval+evidence completion gates; authenticate tenant identity; add durable provider dispatch claims and billing reconciliation. Do not apply to production or enable autonomous execution.
