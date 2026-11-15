/**
 * Bridge to the iOS app's StoreKit when the IDE runs inside the AEP-X iOS wrapper.
 *
 * App Store rules require digital subscriptions bought inside an iOS app to use in-app purchase, so in the
 * wrapper the Subscribe button asks the native side to run StoreKit (bound to our account_id via
 * appAccountToken). The native side hands back only the transaction's originalID; this page verifies it with
 * the backend using its own session, so no token ever crosses the bridge.
 */
export type NativeBridge = { postMessage(message: unknown): void };

export const APPSTORE_EVENT = "aepx-appstore-transaction";

type WebkitWindow = { webkit?: { messageHandlers?: { aepxStore?: NativeBridge } } };

export function nativeStore(w: unknown = typeof window === "undefined" ? undefined : window): NativeBridge | null {
  const handler = (w as WebkitWindow | undefined)?.webkit?.messageHandlers?.aepxStore;
  return handler && typeof handler.postMessage === "function" ? handler : null;
}

/** originalID is a UInt64 rendered as decimal; anything else is ignored. */
export function transactionIdFrom(detail: unknown): string | null {
  const id = (detail as { originalTransactionId?: unknown } | null)?.originalTransactionId;
  return typeof id === "string" && /^\d{1,20}$/.test(id) ? id : null;
}

/** Bundle ID of the iOS app that made the purchase (selects the App Store product server-side). */
export function bundleIdFrom(detail: unknown): string | undefined {
  const id = (detail as { bundleId?: unknown } | null)?.bundleId;
  return typeof id === "string" && /^[A-Za-z0-9.-]{1,155}$/.test(id) ? id : undefined;
}
