package com.equalitysoftware.aepx.companion.billing

import org.json.JSONObject

/** Server-side entitlement (GET /api/v1/entitlement). The backend is the only source of truth. */
data class Entitlement(
    val plan: String,
    val adRate: Double,
    val subscribed: Boolean,
    val trialDaysLeft: Int,
    val price: String,
    val accountId: String,
    val source: String?,
) {
    /** A subscription bought on another store is managed there; the Play button is hidden for it. */
    val canBuyOnPlay: Boolean get() = !subscribed

    val label: String get() = when (plan) {
        "trial" -> "Free trial · $trialDaysLeft days left"
        "pro" -> "Pro · 95% fewer ads"
        else -> "Free plan · ads supported"
    }

    companion object {
        private val UUID = Regex("^[0-9a-fA-F-]{36}$")

        fun parse(body: String): Entitlement {
            val o = JSONObject(body)
            val plan = o.getString("plan")
            require(plan in setOf("trial", "pro", "free")) { "Unknown plan $plan" }
            val rate = o.getDouble("ad_rate")
            require(rate in 0.0..1.0) { "ad_rate out of range" }
            val account = o.getString("account_id")
            require(UUID.matches(account)) { "Invalid account id" }
            return Entitlement(plan, rate, o.optBoolean("subscribed"), o.optInt("trial_days_left"),
                o.optString("price", "£4.99/month"), account, if (o.isNull("source")) null else o.optString("source"))
        }
    }
}

/** Subscription offer as returned by Play; kept free of Billing types for JVM tests. */
data class Offer(val basePlanId: String, val offerId: String?, val token: String)

object OfferPolicy {
    /**
     * The 30-day trial is granted by our backend, so Play-side free-trial offers must not stack on it:
     * always buy the plain base plan (offerId == null).
     */
    fun choose(offers: List<Offer>): Offer? = offers.firstOrNull { it.offerId == null }
}
