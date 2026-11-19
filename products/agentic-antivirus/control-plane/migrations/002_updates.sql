-- Signed update bundles (OPS-02, THR-06, ARC-03): detection rule sets and agent releases.
-- Global (not tenant scoped): every tenant's agents receive the same signed content.
CREATE TABLE aav.update_bundles (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind        text NOT NULL CHECK (kind IN ('detections', 'agent')),
  version     text NOT NULL,
  body        jsonb NOT NULL,
  signature   text NOT NULL,
  key_id      text NOT NULL,
  published_by uuid REFERENCES aav.users(id),
  published_at timestamptz NOT NULL DEFAULT now(),
  revoked_at  timestamptz,
  UNIQUE (kind, version)
);
GRANT SELECT, INSERT ON aav.update_bundles TO aav_app;
GRANT UPDATE (revoked_at) ON aav.update_bundles TO aav_app;
