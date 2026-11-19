"use client";
import { Shell } from "../../components/Shell";
import { Act, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

export default function Quarantine() {
  const { t, locale } = useI18n();
  const d = useApi<any[]>("/v1/quarantine");
  const ask = (msg: string) => window.prompt(msg)?.trim() ?? "";
  return (
    <Shell>
      <h1>{t("nav.quarantine")}</h1>
      <p className="lede">{t("warning.quarantined")} A file is restored only after an administrator gives a reason and a fresh scan on the device finds it clean.</p>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("ui.file")}</th><th>{t("devices.hostname")}</th><th>{t("ui.detection")}</th><th>{t("ui.sha_256")}</th><th>{t("ui.when")}</th><th>{t("ui.status")}</th><th /></tr></thead>
        <tbody>{(d.data ?? []).map((q) => <tr key={q.id}><td>{q.original_path}</td><td>{q.hostname}</td><td>{q.detection} ({q.rule_version})</td>
          <td><code>{q.sha256.slice(0, 16)}…</code></td><td>{formatDateTime(q.quarantined_at, locale)}</td>
          <td>{q.status}{q.restore_scan && q.restore_scan.clean === false ? " (rescan still detects it)" : ""}</td>
          <td className="row">
            {q.status === "quarantined" && <Act label={t("quarantine.request_review")} run={async () => {
              const reason = ask(t("quarantine.reason")); if (reason.length < 3) throw new Error("A reason is required.");
              return api(`/v1/quarantine/${q.id}/request-review`, { body: { reason } }); }} onDone={d.reload} />}
            {["quarantined", "review_requested"].includes(q.status) && <Act label={t("quarantine.restore")} run={async () => {
              const reason = ask(t("quarantine.reason")); if (reason.length < 3) throw new Error("A reason is required.");
              return api(`/v1/quarantine/${q.id}/restore`, { body: { reason } }); }} onDone={d.reload} />}
          </td></tr>)}</tbody></table>
    </Shell>);
}
