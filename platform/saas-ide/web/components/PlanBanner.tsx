"use client";
import { useState } from "react";
import type { Entitlement, IdeApi } from "../lib/api";

type Props = { api: IdeApi | null; entitlement: Entitlement | null; onStatus: (m: string) => void };

/** Header plan chip: trial countdown / Pro / Free, with Subscribe or Manage (Stripe-hosted). */
export default function PlanBanner({ api, entitlement, onStatus }: Props) {
  const [busy, setBusy] = useState(false);
  if (!api || !entitlement) return null;

  async function go(kind: "checkout" | "portal") {
    if (!api) return;
    setBusy(true);
    try {
      const { url } = kind === "checkout" ? await api.stripeCheckout() : await api.stripePortal();
      window.location.assign(url); // Stripe-hosted page; URL is validated server-side
    } catch (e) {
      onStatus(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const e = entitlement;
  const label = e.plan === "pro"
    ? `Pro · ${e.will_renew ? "renews" : "ends"} ${e.renews_at ? new Date(e.renews_at).toLocaleDateString() : ""}`
    : e.plan === "trial"
      ? `Free trial · ${e.trial_days_left} day${e.trial_days_left === 1 ? "" : "s"} left`
      : "Free plan";
  return <div className="plan" role="status" aria-label="Subscription">
    <span className={"badge " + (e.plan === "pro" ? "succeeded" : "pending")}>{label}</span>
    {e.plan !== "pro" && <button className="primary" disabled={busy} onClick={() => void go("checkout")}
      title="Subscribers see 95% fewer ads">Subscribe {e.price} · 95% fewer ads</button>}
    {e.plan === "pro" && e.can_manage_on_web && <button disabled={busy} onClick={() => void go("portal")}>
      Manage subscription</button>}
  </div>;
}
