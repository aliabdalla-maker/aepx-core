-- Audit 27 Nov 2026: a live API key had been typed into integrations.secret_ref (a reference field, stored in
-- clear text). Remove any value that looks like a credential; the owner must store it with PUT .../secret and
-- revoke the exposed key at the provider. The scrub itself is recorded in the audit log.
WITH scrubbed AS (
  UPDATE aav.integrations SET secret_ref = NULL
  WHERE secret_ref ~ '^(sk-|sk_|pk_|rk_|ghp_|gho_|github_pat_|xox|AKIA|ASIA|AIza|ya29\.|eyJ|glpat-)'
     OR (length(secret_ref) >= 32 AND secret_ref !~ '\s' AND secret_ref ~ '[0-9]' AND secret_ref ~ '[a-z]')
  RETURNING id, tenant_id)
INSERT INTO aav.audit_log (tenant_id, actor, action, target, detail)
SELECT tenant_id, 'operator:migration-008', 'integration.secret_ref_scrubbed', id::text,
       '{"reason": "value looked like a credential; revoke it at the provider and store it with PUT /secret"}'::jsonb
FROM scrubbed;
