package com.equalitysoftware.aepx.companion.billing

import android.app.Activity
import android.util.Log
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams
import com.android.billingclient.api.queryPurchasesAsync
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * Google Play Billing for the £4.99/month subscription.
 *
 * The app never grants anything itself: each purchase token goes to POST /api/v1/billing/google-play/verify,
 * where the backend checks it with the Play Developer API, matches obfuscatedExternalAccountId to the signed-in
 * account and acknowledges it. [onPurchaseToken] is that call.
 */
class PlayBilling(
    private val activity: Activity,
    private val productId: String,
    private val onPurchaseToken: (String) -> Unit,
) : PurchasesUpdatedListener {
    private val client = BillingClient.newBuilder(activity)
        .setListener(this)
        .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())
        .build()

    private suspend fun connected(): Boolean {
        if (client.isReady) return true
        return suspendCancellableCoroutine { cont ->
            client.startConnection(object : BillingClientStateListener {
                override fun onBillingSetupFinished(result: BillingResult) {
                    if (cont.isActive) cont.resume(result.responseCode == BillingClient.BillingResponseCode.OK)
                }
                override fun onBillingServiceDisconnected() {
                    if (cont.isActive) cont.resume(false)
                }
            })
        }
    }

    /** Billing Library 8: the listener receives a QueryProductDetailsResult (unfetched products are listed separately). */
    private suspend fun productDetails(query: QueryProductDetailsParams): ProductDetails? =
        suspendCancellableCoroutine { cont ->
            client.queryProductDetailsAsync(query) { result, detailsResult ->
                val found = if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                    detailsResult.productDetailsList.firstOrNull()
                } else {
                    Log.i(TAG, "Product details unavailable: ${result.responseCode}")
                    null
                }
                if (cont.isActive) cont.resume(found)
            }
        }

    /** Starts the Play purchase sheet. Returns a user-facing error, or null when the sheet opened. */
    suspend fun subscribe(accountId: String): String? {
        if (!connected()) return "Google Play billing is unavailable"
        val query = QueryProductDetailsParams.newBuilder().setProductList(listOf(
            QueryProductDetailsParams.Product.newBuilder()
                .setProductId(productId).setProductType(BillingClient.ProductType.SUBS).build()
        )).build()
        val details = productDetails(query) ?: return "Subscription is not available in this store yet"
        val offers = details.subscriptionOfferDetails.orEmpty().map { Offer(it.basePlanId, it.offerId, it.offerToken) }
        val offer = OfferPolicy.choose(offers) ?: return "Subscription has no base plan"
        val params = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(listOf(
                BillingFlowParams.ProductDetailsParams.newBuilder()
                    .setProductDetails(details).setOfferToken(offer.token).build()
            ))
            .setObfuscatedAccountId(accountId) // backend rejects tokens bound to another account
            .build()
        val result = client.launchBillingFlow(activity, params)
        return if (result.responseCode == BillingClient.BillingResponseCode.OK) null else "Purchase could not start (${result.responseCode})"
    }

    /** Re-sends existing subscription tokens (reinstall / new device). */
    suspend fun restore() {
        if (!connected()) return
        val params = QueryPurchasesParams.newBuilder().setProductType(BillingClient.ProductType.SUBS).build()
        client.queryPurchasesAsync(params).purchasesList
            .filter { it.purchaseState == Purchase.PurchaseState.PURCHASED && productId in it.products }
            .forEach { onPurchaseToken(it.purchaseToken) }
    }

    override fun onPurchasesUpdated(result: BillingResult, purchases: MutableList<Purchase>?) {
        if (result.responseCode != BillingClient.BillingResponseCode.OK) {
            Log.i(TAG, "Purchase not completed: ${result.responseCode}")
            return
        }
        purchases.orEmpty()
            .filter { it.purchaseState == Purchase.PurchaseState.PURCHASED }
            .forEach { onPurchaseToken(it.purchaseToken) }
    }

    fun close() = client.endConnection()

    companion object { private const val TAG = "AepxBilling" }
}
