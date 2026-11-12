-- Phase 2.18 forward migration for databases already initialized at 2.14.
-- Run once as migration role, not ide_runtime. No live execution is enabled.
ALTER TABLE ide_mcp_executions
  ALTER COLUMN reconciliation_reference TYPE VARCHAR(4096);
