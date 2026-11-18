package com.equalitysoftware.agenticantivirus.ads

import android.app.Activity
import android.util.Log
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.AdSize
import com.google.android.gms.ads.AdView
import com.google.android.gms.ads.LoadAdError
import com.google.android.gms.ads.MobileAds
import com.google.android.gms.ads.appopen.AppOpenAd
import com.google.android.ump.ConsentInformation
import com.google.android.ump.ConsentRequestParameters
import com.google.android.ump.UserMessagingPlatform
import java.util.concurrent.atomic.AtomicBoolean

/** Consent-first AdMob: MobileAds initialises only after UMP allows ad requests (GDPR/UK). */
class AdsRuntime(private val activity: Activity, private val registry: AdUnitRegistry) {
    private val consent: ConsentInformation = UserMessagingPlatform.getConsentInformation(activity)
    private val started = AtomicBoolean(false)
    private val appOpenShown = AtomicBoolean(false)
    private var pacer: AdPacer? = null

    fun start() {
        consent.requestConsentInfoUpdate(activity, ConsentRequestParameters.Builder().build(), {
            UserMessagingPlatform.loadAndShowConsentFormIfRequired(activity) { initIfAllowed() }
        }, { e -> Log.w(TAG, "consent update failed: ${e.message}") })
        initIfAllowed()
    }

    private fun initIfAllowed() {
        if (consent.canRequestAds() && started.compareAndSet(false, true)) {
            MobileAds.initialize(activity) { maybeAppOpen() }
        }
    }

    fun onRateKnown(p: AdPacer) { pacer = p; maybeAppOpen() }

    private fun ready() = started.get() && consent.canRequestAds()

    private fun maybeAppOpen() {
        val p = pacer ?: return
        if (!ready() || !appOpenShown.compareAndSet(false, true) || !p.next()) return
        val unit = registry.unitFor(Placement.APP_OPEN) ?: return
        AppOpenAd.load(activity, unit, AdRequest.Builder().build(), object : AppOpenAd.AppOpenAdLoadCallback() {
            override fun onAdLoaded(ad: AppOpenAd) = ad.show(activity)
            override fun onAdFailedToLoad(e: LoadAdError) { Log.i(TAG, "app open unavailable: ${e.code}") }
        })
    }

    /** A banner view for the placement, or null when ads must not show there. */
    fun banner(p: Placement): AdView? {
        if (!ready() || pacer == null) return null
        val unit = registry.unitFor(p) ?: return null
        return AdView(activity).apply {
            setAdSize(AdSize.BANNER)
            adUnitId = unit
            contentDescription = "Advertisement"
            loadAd(AdRequest.Builder().build())
        }
    }

    companion object { private const val TAG = "AavAds" }
}
