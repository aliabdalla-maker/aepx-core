"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatCurrency, formatDateTime } from "../../lib/format";

const POLICIES: Record<string, string> = {
  paywall_console_keep_protection: "Console needs a subscription; devices stay protected",
  free_with_full_ads: "Keep everything free with full adverts",
  lock_all: "Stop everything, including device protection, until someone pays",
};

export default function Billing() {
  const { t, locale } = useI18n();
  const e = useApi<any>("/v1/licence");
  const me = useApi<any>("/v1/auth/me");
  const devices = useApi<any[]>("/v1/devices");
  const [device, setDevice] = useState("");
  const android = typeof window !== "undefined" ? (window as any).AavAndroid : undefined;
  const [unit, setUnit] = useState("per_user");
  const [policy, setPolicy] = useState("paywall_console_keep_protection");
  const [ack, setAck] = useState(false);
  return (
    <Shell>
      <h1>{t("nav.billing")}</h1>
      <Status error={e.error} loading={!e.data} />
      {e.data && <>
        <p className="lede">{formatCurrency(4.99, "GBP", locale)} per month for each {e.data.licence_unit === "per_user" ? "user" : "device"}.
          The first 30 days are free with adverts. Subscribing reduces adverts by 95%.</p>
        <div className="stats">
          <div><strong>{e.data.state}</strong><span>subscription state</span></div>
          <div><strong>{e.data.state === "trial" ? e.data.trial_days_left : "—"}</strong><span>trial days left</span></div>
          <div><strong>{Math.round(e.data.ad_rate * 100)}%</strong><span>of adverts shown</span></div>
          <div><strong>{e.data.paid_until ? formatDateTime(e.data.paid_until, locale) : "—"}</strong><span>paid until</span></div>
        </div>
        <h2>Subscribe</h2>
        {android ? (e.data.licence_unit === "per_user"
          ? <button className="primary" onClick={() => android.subscribe("user", me.data?.id)}>Subscribe for {formatCurrency(4.99, "GBP", locale)} a month with Google Play</button>
          : <div className="row"><select aria-label="Device to license" value={device} onChange={(ev) => setDevice(ev.target.value)}>
              <option value="">Choose a device</option>{(devices.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.hostname}</option>)}</select>
              <button className="primary" disabled={!device} onClick={() => android.subscribe("device", device)}>Subscribe this device with Google Play</button></div>)
          : <p>On Android, subscribe in the Agentic Antivirus app through Google Play. On iPhone and iPad, App Store subscriptions are not available yet. Paying on the web is not available yet.</p>}
        <h2>Licensing rules</h2>
        <div className="form">
          <label>Charge<select value={unit} onChange={(ev) => setUnit(ev.target.value)}>
            <option value="per_user">Per user (covers all of their devices)</option><option value="per_device">Per device</option></select></label>
          <label>When the trial ends without payment<select value={policy} onChange={(ev) => setPolicy(ev.target.value)}>
            {Object.entries(POLICIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          {policy === "lock_all" && <label style={{ display: "flex", gap: ".5rem", fontWeight: 400 }} className="banner warn">
            <input type="checkbox" checked={ack} onChange={(ev) => setAck(ev.target.checked)} />
            I understand devices will stop scanning and blocking threats after the trial until a subscription is paid.</label>}
          <Act className="primary" label="Save licensing rules" run={() => api("/v1/licence/settings", { method: "PUT",
            body: { licence_unit: unit, post_trial_policy: policy, acknowledge_lock_all_disables_protection: ack } })} onDone={e.reload} />
        </div>
      </>}
    </Shell>);
}
