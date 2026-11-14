package com.equalitysoftware.aepx.companion.ads

import android.app.Activity
import android.graphics.Color
import android.os.SystemClock
import android.util.Log
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.google.android.gms.ads.AdError
import com.google.android.gms.ads.AdLoader
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.AdSize
import com.google.android.gms.ads.AdView
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError
import com.google.android.gms.ads.MobileAds
import com.google.android.gms.ads.appopen.AppOpenAd
import com.google.android.gms.ads.interstitial.InterstitialAd
import com.google.android.gms.ads.interstitial.InterstitialAdLoadCallback
import com.google.android.gms.ads.nativead.NativeAd
import com.google.android.gms.ads.nativead.NativeAdView
import com.google.android.ump.ConsentInformation
import com.google.android.ump.ConsentRequestParameters
import com.google.android.ump.UserMessagingPlatform
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Consent-first AdMob runtime. MobileAds is initialised only after the UMP consent flow says ads may be
 * requested AND the registry has at least one configured placement. Approval/decision screens never host ads.
 */
class AdsRuntime(val activity: Activity, val registry: AdUnitRegistry) {
    private val consent: ConsentInformation = UserMessagingPlatform.getConsentInformation(activity)
    private val started = AtomicBoolean(false)
    private val interstitialCap = FrequencyCap(3 * 60_000L, 3) { SystemClock.elapsedRealtime() }
    private val appOpenCap = FrequencyCap(4 * 60 * 60_000L, 1) { SystemClock.elapsedRealtime() }
    private var interstitial: InterstitialAd? = null

    var ready by mutableStateOf(false)
        private set

    val privacyOptionsRequired: Boolean
        get() = consent.privacyOptionsRequirementStatus ==
            ConsentInformation.PrivacyOptionsRequirementStatus.REQUIRED

    fun start() {
        val params = ConsentRequestParameters.Builder().build()
        consent.requestConsentInfoUpdate(activity, params, {
            UserMessagingPlatform.loadAndShowConsentFormIfRequired(activity) { error ->
                if (error != null) Log.w(TAG, "Consent form: ${error.message}")
                initializeIfAllowed()
            }
        }, { error ->
            Log.w(TAG, "Consent update failed: ${error.message}")
            initializeIfAllowed() // may still use consent obtained in a previous session
        })
        initializeIfAllowed()
    }

    fun showPrivacyOptions() {
        UserMessagingPlatform.showPrivacyOptionsForm(activity) { error ->
            if (error != null) Log.w(TAG, "Privacy options: ${error.message}")
        }
    }

    private fun initializeIfAllowed() {
        if (!registry.mayInitialize(consent.canRequestAds())) return
        if (!started.compareAndSet(false, true)) return
        MobileAds.initialize(activity) {
            ready = true
            preloadInterstitial()
            showAppOpenOnce()
        }
    }

    private fun preloadInterstitial() {
        val unit = registry.unitFor(Placement.RUN_COMPLETED_INTERSTITIAL) ?: return
        InterstitialAd.load(activity, unit, AdRequest.Builder().build(), object : InterstitialAdLoadCallback() {
            override fun onAdLoaded(ad: InterstitialAd) { interstitial = ad }
            override fun onAdFailedToLoad(error: LoadAdError) { interstitial = null }
        })
    }

    /** Natural break only: called when the user leaves a finished run, never on an approval screen. */
    fun onLeftCompletedRun() {
        val ad = interstitial ?: return
        if (!interstitialCap.tryAcquire()) return
        interstitial = null
        ad.fullScreenContentCallback = object : FullScreenContentCallback() {
            override fun onAdDismissedFullScreenContent() { preloadInterstitial() }
            override fun onAdFailedToShowFullScreenContent(error: AdError) { preloadInterstitial() }
        }
        ad.show(activity)
    }

    private fun showAppOpenOnce() {
        val unit = registry.unitFor(Placement.APP_OPEN) ?: return
        AppOpenAd.load(activity, unit, AdRequest.Builder().build(), object : AppOpenAd.AppOpenAdLoadCallback() {
            override fun onAdLoaded(ad: AppOpenAd) { if (appOpenCap.tryAcquire()) ad.show(activity) }
            override fun onAdFailedToLoad(error: LoadAdError) { Log.i(TAG, "App open ad unavailable: ${error.code}") }
        })
    }

    companion object { private const val TAG = "AepxAds" }
}

@Composable
fun BannerSlot(runtime: AdsRuntime?, placement: Placement, modifier: Modifier = Modifier) {
    val unit = if (placement.format == AdFormat.BANNER) runtime?.registry?.unitFor(placement) else null
    if (runtime == null || !runtime.ready || unit == null) return
    AndroidView(
        modifier = modifier.fillMaxWidth(),
        factory = { context ->
            AdView(context).apply {
                adUnitId = unit
                val widthDp = context.resources.configuration.screenWidthDp
                setAdSize(AdSize.getCurrentOrientationAnchoredAdaptiveBannerAdSize(context, widthDp))
                loadAd(AdRequest.Builder().build())
            }
        },
        onRelease = { it.destroy() },
    )
}

@Composable
fun NativeFeedSlot(runtime: AdsRuntime?, modifier: Modifier = Modifier) {
    val unit = runtime?.registry?.unitFor(Placement.NATIVE_FEED)
    val ready = runtime?.ready == true
    var ad by remember { mutableStateOf<NativeAd?>(null) }
    DisposableEffect(unit, ready) {
        if (runtime != null && ready && unit != null) {
            AdLoader.Builder(runtime.activity, unit)
                .forNativeAd { loaded -> ad?.destroy(); ad = loaded }
                .build()
                .loadAd(AdRequest.Builder().build())
        }
        onDispose { ad?.destroy(); ad = null }
    }
    val loaded = ad ?: return
    AndroidView(modifier = modifier.fillMaxWidth(), factory = { context ->
        val headline = TextView(context).apply { textSize = 16f; setTextColor(Color.WHITE) }
        val body = TextView(context).apply { setTextColor(Color.LTGRAY) }
        val label = TextView(context).apply { text = "Ad"; setTextColor(Color.parseColor("#FFE08A")) }
        val cta = Button(context)
        val column = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 16, 24, 16)
            addView(label); addView(headline); addView(body); addView(cta)
        }
        NativeAdView(context).apply {
            addView(column)
            headlineView = headline
            bodyView = body
            callToActionView = cta
        }
    }, update = { view ->
        (view.headlineView as TextView).text = loaded.headline
        (view.bodyView as TextView).text = loaded.body ?: ""
        (view.callToActionView as Button).text = loaded.callToAction ?: "Open"
        view.setNativeAd(loaded)
    })
}
