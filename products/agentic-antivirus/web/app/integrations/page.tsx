"use client";
import { useI18n } from "../../lib/i18n";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";

const KINDS = ["identity", "dns", "firewall", "waf", "api_gateway", "ddos", "cdn", "load_balancer", "backup", "dlp", "cloud_audit",
  "email", "url_reputation", "physical", "vulnerability", "smtp", "other"];
const PROTOCOLS = ["webhook", "rest", "openapi", "graphql", "grpc", "mcp", "oauth2", "oidc", "smtp", "imap", "sftp", "amqp", "mqtt", "sql"];
const MATURITY: Record<string, string> = { verified_live: "integration.maturity.verified_live", test_only: "integration.maturity.test_only", stub: "integration.maturity.stub", unavailable: "integration.maturity.unavailable" };

export default function Integrations() {
  const { t } = useI18n();
  const d = useApi<any[]>("/v1/integrations");
  const cov = useApi<any[]>("/v1/coverage");
  const [f, setF] = useState({ name: "", signal_kind: "identity", protocol: "webhook", endpoint: "", secret_ref: "" });
  const [created, setCreated] = useState<any>(null);
  return (
    <Shell>
      <h1>{t("nav.integrations")}</h1>
      <p className="lede">{t("integration.lede")}</p>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("ui.name")}</th><th>{t("ui.signal")}</th><th>{t("ui.protocol")}</th><th>{t("ui.endpoint")}</th><th>{t("ui.maturity")}</th><th>{t("ui.health")}</th><th /></tr></thead>
        <tbody>{(d.data ?? []).map((i) => <tr key={i.id}><td>{i.name}</td><td>{i.signal_kind}</td><td>{i.protocol}</td>
          <td>{i.endpoint || t("integration.inbound")}</td><td>{t(MATURITY[i.maturity])}</td>
          <td>{i.last_health ? (i.last_health.ok ? "reachable under egress policy" : i.last_health.reason) : "not checked"}</td>
          <td className="row"><Act label={t("ui.check")} run={() => api(`/v1/integrations/${i.id}/health`, { method: "POST" })} onDone={d.reload} />
            {i.maturity === "unavailable" && <Act label={t("ui.accept_test_data")} run={() => api(`/v1/integrations/${i.id}/maturity`,
              { body: { maturity: "test_only", provider: i.config?.provider ?? "unspecified", evidence: {} } })} onDone={d.reload} />}</td></tr>)}</tbody></table>

      <h2>{t("ui.add_an_integration")}</h2>
      <div className="form">
        <label>{t("ui.name")}<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label>{t("ui.signal")}<select value={f.signal_kind} onChange={(e) => setF({ ...f, signal_kind: e.target.value })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></label>
        <label>{t("ui.protocol")}<select value={f.protocol} onChange={(e) => setF({ ...f, protocol: e.target.value })}>{PROTOCOLS.map((k) => <option key={k}>{k}</option>)}</select></label>
        <label>{t("ui.endpoint")} <span className="hint">{t("ui.tls_only_must_be_on_the")}</span><input value={f.endpoint} onChange={(e) => setF({ ...f, endpoint: e.target.value })} /></label>
        <label>{t("ui.secret_reference")} <span className="hint">{t("ui.name_of_the_secret_in_your")}</span>
          <input value={f.secret_ref} onChange={(e) => setF({ ...f, secret_ref: e.target.value })} /></label>
        <Act className="primary" label={t("ui.add_integration")} run={() => api("/v1/integrations", { body: { ...f, secret_ref: f.secret_ref || null } })}
          onDone={(r) => { setCreated(r); d.reload(); }} />
        {created && <div className="banner" role="status">{t("ui.webhook")} <code>{created.webhook_url}</code>. {t("integration.secretOnce")} <code style={{ overflowWrap: "anywhere" }}>{created.webhook_secret}</code></div>}
      </div>

      <h2>{t("ui.coverage_by_protection_layer")}</h2>
      <table><thead><tr><th>{t("ui.layer")}</th><th>{t("ui.available_signals")}</th><th>{t("ui.gaps")}</th></tr></thead>
        <tbody>{(cov.data ?? []).map((c) => <tr key={c.layer}><td>{c.layer}</td><td>{c.available_signals.join(", ") || "none"}</td>
          <td>{c.gaps.join("; ") || "none"}</td></tr>)}</tbody></table>
    </Shell>);
}
