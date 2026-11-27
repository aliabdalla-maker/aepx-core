-- INT-02 / INT-03: MQTT (IoT), AMQP and SFTP join SQL and IMAP as pulled transports.
CREATE OR REPLACE FUNCTION aav.pollable_integrations()
RETURNS TABLE (id uuid, tenant_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
  SELECT id, tenant_id FROM aav.integrations
  WHERE enabled AND maturity IN ('verified_live', 'test_only') AND protocol IN ('sql', 'imap', 'mqtt', 'amqp', 'sftp')
$$;
REVOKE ALL ON FUNCTION aav.pollable_integrations() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.pollable_integrations() TO aav_app;

-- INT-03 outbound connectors: messaging (Slack, Teams), CRM (HubSpot), ITSM (ServiceNow).
ALTER TABLE aav.integrations DROP CONSTRAINT IF EXISTS integrations_signal_kind_check;
ALTER TABLE aav.integrations ADD CONSTRAINT integrations_signal_kind_check CHECK (signal_kind IN (
  'identity', 'dns', 'firewall', 'waf', 'api_gateway', 'ddos', 'cdn', 'load_balancer', 'backup', 'dlp', 'cloud_audit',
  'email', 'url_reputation', 'physical', 'vulnerability', 'smtp', 'other', 'messaging', 'crm', 'itsm'));
