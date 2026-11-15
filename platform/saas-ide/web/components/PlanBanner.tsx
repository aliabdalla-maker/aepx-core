"use client";
import { useEffect, useState } from "react";
import type { Entitlement, IdeApi } from "../lib/api";
import { APPSTORE_EVENT, bundleIdFrom, nativeStore, transactionIdFrom } from "../lib/nativeStore";

type Props = {
  api: IdeApi | null; entitlement: Entitlement | null;
  onStatus: (m: string) => void; onEntitlement: (e: Entitlement) => void;
};

/**
 * Header plan chip: trial countdown / Pro / Free, with Subscribe or Manage.
 * Web and desktop use Stripe-hosted pages; inside the iOS app the purchase goes through StoreKit.
 */
export default function PlanBanner({ api, entitlement, onStatus, onEntitlement }: Props) {
  const [busy, setBusy] = useState(false);
  const [bridge] = useState(() => nativeStore());

  useEffect(() => {
    if (!bridge || !api) return;
    const onTransaction = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      const id = transactionIdFrom(detail);
      if (!id) return;
      api.appStoreVerify(id, bundleIdFrom(detail))
        .then((e) => { onEntitlement(e); bridge.postMessage({ type: "verified", originalTransactionId: id, ok: true }); })
        .catch((e) => {
          bridge.postMessage({ type: "verified", originalTransactionId: id, ok: false });
          onStatus(e instanceof Error ? e.message : String(e));
        })
        .finally(() => setBusy(false));
    };
    window.addEventListener(APPSTORE_EVENT, onTransaction);
    return () => window.removeEventListener(APPSTORE_EVENT, onTransaction);
  }, [bridge, api, onEntitlement, onStatus]);

  if (!api || !entitlement) return null;
  const e = entitlement;

  async function go(kind: "checkout" | "portal") {
    if (!api) return;
    setBusy(true);
    try {
      const { url } = kind === "checkout" ? await api.stripeCheckout() : await api.stripePortal();
      window.location.assign(url); // Stripe-hosted page; URL is validated server-side
    } catch (err) {
      onStatus(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  function subscribe() {
    if (bridge) { setBusy(true); bridge.postMessage({ type: "subscribe", accountId: e.account_id }); }
    else void go("checkout");
  }

  const label = e.plan === "pro"
    ? `Pro · ${e.will_renew ? "renews" : "ends"} ${e.renews_at ? new Date(e.renews_at).toLocaleDateString() : ""}`
    : e.plan === "trial"
      ? `Free trial · ${e.trial_days_left} day${e.trial_days_left === 1 ? "" : "s"} left`
      : "Free plan";
  return <div className="plan" role="status" aria-label="Subscription">
    <span className={"badge " + (e.plan === "pro" ? "succeeded" : "pending")}>{label}</span>
    {e.plan !== "pro" && <button className="primary" disabled={busy} onClick={subscribe}
      title="Subscribers see 95% fewer ads">Subscribe {e.price} · 95% fewer ads</button>}
    {e.plan === "pro" && !bridge && e.can_manage_on_web && <button disabled={busy} onClick={() => void go("portal")}>
      Manage subscription</button>}
    {e.plan === "pro" && bridge && e.source === "app_store" &&
      <button onClick={() => bridge.postMessage({ type: "manage" })}>Manage subscription</button>}
  </div>;
}
