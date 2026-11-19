"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";

const KINDS = ["identity", "dns", "firewall", "waf", "api_gateway", "ddos", "cdn", "load_balancer", "backup", "dlp", "cloud_audit",
  "email", "url_reputation", "physical", "vulnerability", "smtp", "other"];
const PROTOCOLS = ["webhook", "rest", "openapi", "graphql", "grpc", "mcp", "oauth2", "oidc", "smtp", "imap", "sftp", "amqp", "mqtt", "sql"];
const MATURITY: Record<string, string> = { verified_live: "Live (verified)", test_only: "Test data only", stub: "Not connected (stub)",
  unavailable: "Not available" };

export default function Integrations() {
  const d = useApi<any[]>("/v1/integrations");
  const cov = useApi<any[]>("/v1/coverage");
  const [f, setF] = useState({ name: "", signal_kind: "identity", protocol: "webhook", endpoint: "", secret_ref: "" });
  const [created, setCreated] = useState<any>(null);
  return (
    <Shell>
      <h1>Integrations</h1>
      <p className="lede">Signals from your identity provider, DNS, firewalls and other tools. New integrations start as not available; only a provider adapter that passed its contract test can be marked live. Test data is labelled as simulation everywhere it appears.</p>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>Name</th><th>Signal</th><th>Protocol</th><th>Endpoint</th><th>Maturity</th><th>Health</th><th /></tr></thead>
        <tbody>{(d.data ?? []).map((i) => <tr key={i.id}><td>{i.name}</td><td>{i.signal_kind}</td><td>{i.protocol}</td>
          <td>{i.endpoint || "inbound webhook"}</td><td>{MATURITY[i.maturity]}</td>
          <td>{i.last_health ? (i.last_health.ok ? "reachable under egress policy" : i.last_health.reason) : "not checked"}</td>
          <td className="row"><Act label="Check" run={() => api(`/v1/integrations/${i.id}/health`, { method: "POST" })} onDone={d.reload} />
            {i.maturity === "unavailable" && <Act label="Accept test data" run={() => api(`/v1/integrations/${i.id}/maturity`,
              { body: { maturity: "test_only", provider: i.config?.provider ?? "unspecified", evidence: {} } })} onDone={d.reload} />}</td></tr>)}</tbody></table>

      <h2>Add an integration</h2>
      <div className="form">
        <label>Name<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label>Signal<select value={f.signal_kind} onChange={(e) => setF({ ...f, signal_kind: e.target.value })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></label>
        <label>Protocol<select value={f.protocol} onChange={(e) => setF({ ...f, protocol: e.target.value })}>{PROTOCOLS.map((k) => <option key={k}>{k}</option>)}</select></label>
        <label>Endpoint <span className="hint">TLS only, must be on the egress allowlist</span><input value={f.endpoint} onChange={(e) => setF({ ...f, endpoint: e.target.value })} /></label>
        <label>Secret reference <span className="hint">Name of the secret in your secret store, never the secret itself</span>
          <input value={f.secret_ref} onChange={(e) => setF({ ...f, secret_ref: e.target.value })} /></label>
        <Act className="primary" label="Add integration" run={() => api("/v1/integrations", { body: { ...f, secret_ref: f.secret_ref || null } })}
          onDone={(r) => { setCreated(r); d.reload(); }} />
        {created && <div className="banner" role="status">Webhook: <code>{created.webhook_url}</code>. Secret (shown once): <code style={{ overflowWrap: "anywhere" }}>{created.webhook_secret}</code></div>}
      </div>

      <h2>Coverage by protection layer</h2>
      <table><thead><tr><th>Layer</th><th>Available signals</th><th>Gaps</th></tr></thead>
        <tbody>{(cov.data ?? []).map((c) => <tr key={c.layer}><td>{c.layer}</td><td>{c.available_signals.join(", ") || "none"}</td>
          <td>{c.gaps.join("; ") || "none"}</td></tr>)}</tbody></table>
    </Shell>);
}
