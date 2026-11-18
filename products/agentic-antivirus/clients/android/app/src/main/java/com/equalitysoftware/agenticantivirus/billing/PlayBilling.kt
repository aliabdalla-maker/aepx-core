package com.equalitysoftware.agenticantivirus.billing

import android.app.Activity
import android.webkit.JavascriptInterface
import android.webkit.WebView
import com.android.billingclient.api.AcknowledgePurchaseParams
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.acknowledgePurchase
import com.android.billingclient.api.queryProductDetails
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONObject
import kotlin.coroutines.resume

data class Entitlement(val state: String, val adRate: Double, val unit: String)

/** Reads the console's session from the WebView and calls the control plane with it. */
class ConsoleBridge(private val web: WebView, private val consoleUrl: String) {
    private suspend fun js(expr: String): String = suspendCancellableCoroutine { c ->
        web.post { web.evaluateJavascript(expr) { c.resume(it?.trim('"') ?: "") } }
    }

    suspend fun call(method: String, path: String, body: String? = null): JSONObject? {
        val token = js("sessionStorage.getItem('aav.token')")
        val tenant = js("sessionStorage.getItem('aav.tenant')")
        if (token.isEmpty() || token == "null") return null
        return kotlinx.coroutines.withContext(Dispatchers.IO) {
            val url = java.net.URL(consoleUrl.trimEnd('/') + "/api" + path)
            (url.openConnection() as java.net.HttpURLConnection).run {
                requestMethod = method
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("X-Tenant-Id", tenant)
                if (body != null) { doOutput = true; setRequestProperty("Content-Type", "application/json"); outputStream.write(body.toByteArray()) }
                val ok = responseCode in 200..299
                val text = (if (ok) inputStream else errorStream)?.bufferedReader()?.readText() ?: "{}"
                if (ok) JSONObject(text) else null
            }
        }
    }

    suspend fun entitlement(): Entitlement? = call("GET", "/v1/licence")?.let {
        Entitlement(it.getString("state"), it.getDouble("ad_rate"), it.getString("licence_unit"))
    }
}

/** Google Play subscription (GBP 4.99/month). The control plane verifies every purchase token with the
 *  Play Developer API before a licence exists; the app never grants itself an entitlement. */
class PlayBilling(private val activity: Activity, private val productId: String, private val bridge: ConsoleBridge) :
    PurchasesUpdatedListener {
    private val scope = CoroutineScope(Dispatchers.Main)
    private val client = BillingClient.newBuilder(activity).setListener(this)
        .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build()).build()
    private var holder: Pair<String, String>? = null // (holder_kind, holder_id)

    private suspend fun connected(): Boolean = client.isReady || suspendCancellableCoroutine { c ->
        client.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(r: BillingResult) { if (c.isActive) c.resume(r.responseCode == BillingClient.BillingResponseCode.OK) }
            override fun onBillingServiceDisconnected() { if (c.isActive) c.resume(false) }
        })
    }

    fun subscribe(holderKind: String, holderId: String) = scope.launch {
        holder = holderKind to holderId
        if (!connected()) return@launch
        val details = client.queryProductDetails(QueryProductDetailsParams.newBuilder().setProductList(listOf(
            QueryProductDetailsParams.Product.newBuilder().setProductId(productId).setProductType(BillingClient.ProductType.SUBS).build()
        )).build()).productDetailsList?.firstOrNull() ?: return@launch
        val offer = details.subscriptionOfferDetails?.firstOrNull { it.offerId == null } ?: return@launch
        client.launchBillingFlow(activity, BillingFlowParams.newBuilder().setObfuscatedAccountId(holderId)
            .setProductDetailsParamsList(listOf(BillingFlowParams.ProductDetailsParams.newBuilder()
                .setProductDetails(details).setOfferToken(offer.offerToken).build())).build())
    }

    override fun onPurchasesUpdated(r: BillingResult, purchases: MutableList<Purchase>?) {
        if (r.responseCode != BillingClient.BillingResponseCode.OK) return
        purchases?.filter { it.purchaseState == Purchase.PurchaseState.PURCHASED }?.forEach { p ->
            scope.launch {
                val (kind, id) = holder ?: return@launch
                val body = JSONObject().put("purchase_token", p.purchaseToken).put("holder_kind", kind).put("holder_id", id)
                val verified = bridge.call("POST", "/v1/billing/google-play/verify", body.toString())
                if (verified != null && !p.isAcknowledged) {
                    client.acknowledgePurchase(AcknowledgePurchaseParams.newBuilder().setPurchaseToken(p.purchaseToken).build())
                }
            }
        }
    }

    /** Exposed to the console's Subscription page as window.AavAndroid.subscribe(kind, id). */
    fun jsInterface() = object {
        @JavascriptInterface fun subscribe(kind: String, id: String) { this@PlayBilling.subscribe(kind, id) }
        @JavascriptInterface fun available(): Boolean = true
    }

    fun close() = client.endConnection()
}
