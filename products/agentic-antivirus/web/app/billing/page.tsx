"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatCurrency, formatDateTime } from "../../lib/format";

const POLICIES: Record<string, string> = { paywall_console_keep_protection: "billing.policy.paywall_console_keep_protection", free_with_full_ads: "billing.policy.free_with_full_ads", lock_all: "billing.policy.lock_all" };

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
          <div><strong>{e.data.state}</strong><span>{t("ui.subscription_state")}</span></div>
          <div><strong>{e.data.state === "trial" ? e.data.trial_days_left : "—"}</strong><span>{t("ui.trial_days_left")}</span></div>
          <div><strong>{Math.round(e.data.ad_rate * 100)}%</strong><span>{t("ui.of_adverts_shown")}</span></div>
          <div><strong>{e.data.paid_until ? formatDateTime(e.data.paid_until, locale) : "—"}</strong><span>{t("ui.paid_until")}</span></div>
        </div>
        <h2>{t("billing.subscribe")}</h2>
        {android ? (e.data.licence_unit === "per_user"
          ? <button className="primary" onClick={() => android.subscribe("user", me.data?.id)}>Subscribe for {formatCurrency(4.99, "GBP", locale)} a month with Google Play</button>
          : <div className="row"><select aria-label={t("ui.device_to_license")} value={device} onChange={(ev) => setDevice(ev.target.value)}>
              <option value="">{t("ui.choose_a_device")}</option>{(devices.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.hostname}</option>)}</select>
              <button className="primary" disabled={!device} onClick={() => android.subscribe("device", device)}>{t("ui.subscribe_this_device_with_google_play")}</button></div>)
          : <p>{t("ui.on_android_subscribe_in_the_agentic")}</p>}
        <h2>{t("ui.licensing_rules")}</h2>
        <div className="form">
          <label>{t("ui.charge")}<select value={unit} onChange={(ev) => setUnit(ev.target.value)}>
            <option value="per_user">{t("ui.per_user_covers_all_of_their")}</option><option value="per_device">{t("ui.per_device")}</option></select></label>
          <label>{t("ui.when_the_trial_ends_without_payment")}<select value={policy} onChange={(ev) => setPolicy(ev.target.value)}>
            {Object.entries(POLICIES).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></label>
          {policy === "lock_all" && <label style={{ display: "flex", gap: ".5rem", fontWeight: 400 }} className="banner warn">
            <input type="checkbox" checked={ack} onChange={(ev) => setAck(ev.target.checked)} />
            {t("ui.i_understand_devices_will_stop_scanning")}</label>}
          <Act className="primary" label={t("ui.save_licensing_rules")} run={() => api("/v1/licence/settings", { method: "PUT",
            body: { licence_unit: unit, post_trial_policy: policy, acknowledge_lock_all_disables_protection: ack } })} onDone={e.reload} />
        </div>
      </>}
    </Shell>);
}
