package com.equalitysoftware.agenticantivirus

import android.annotation.SuppressLint
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.equalitysoftware.agenticantivirus.ads.AdPacer
import com.equalitysoftware.agenticantivirus.ads.AdUnitRegistry
import com.equalitysoftware.agenticantivirus.ads.AdsConfigParser
import com.equalitysoftware.agenticantivirus.ads.AdsRuntime
import com.equalitysoftware.agenticantivirus.ads.Placement
import com.equalitysoftware.agenticantivirus.ads.RoutePlacement
import com.equalitysoftware.agenticantivirus.billing.ConsoleBridge
import com.equalitysoftware.agenticantivirus.billing.PlayBilling
import kotlinx.coroutines.launch

/**
 * Android client: wraps the accessible web console (same build as the PWA) and adds what only the
 * native app can do — AdMob (consent-first) and Google Play subscriptions verified by the control plane.
 * AdSense is disabled inside the WebView (the console detects the app's user agent).
 */
class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private lateinit var adHost: FrameLayout
    private var ads: AdsRuntime? = null
    private var billing: PlayBilling? = null
    private var pacer = AdPacer(1.0)

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.userAgentString = settings.userAgentString + " AgenticAntivirusApp/" + BuildConfig.VERSION_NAME
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                    // Stay on the console origin; everything else opens in the browser.
                    val console = Uri.parse(BuildConfig.CONSOLE_URL)
                    if (req.url.host == console.host) return false
                    startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, req.url))
                    return true
                }
                override fun onPageFinished(view: WebView, url: String) = onRoute(Uri.parse(url).path ?: "/")
            }
        }
        adHost = FrameLayout(this).apply { visibility = View.GONE }
        root.addView(web)
        root.addView(adHost, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        setContentView(root)

        val bridge = ConsoleBridge(web, BuildConfig.CONSOLE_URL)
        billing = PlayBilling(this, BuildConfig.PLAY_SUBSCRIPTION_ID, bridge)
        web.addJavascriptInterface(billing!!.jsInterface(), "AavAndroid")

        val cfg = runCatching { AdsConfigParser.parse(assets.open("ads-config.json").bufferedReader().readText()) }.getOrNull()
        ads = AdsRuntime(this, AdUnitRegistry(cfg, BuildConfig.DEBUG)).also { it.start() }
        lifecycleScope.launch {
            bridge.entitlement()?.let { pacer = AdPacer(it.adRate); ads?.onRateKnown(pacer) }
        }
        web.loadUrl(BuildConfig.CONSOLE_URL)
    }

    private fun onRoute(path: String) {
        val base = Uri.parse(BuildConfig.CONSOLE_URL).path?.trimEnd('/') ?: ""
        val placement: Placement? = RoutePlacement.forPath(path.removePrefix(base).ifEmpty { "/" })
        adHost.removeAllViews()
        adHost.visibility = View.GONE
        if (placement != null && pacer.next()) {
            ads?.banner(placement)?.let { adHost.addView(it); adHost.visibility = View.VISIBLE }
        }
    }

    override fun onDestroy() {
        billing?.close()
        super.onDestroy()
    }

    @Deprecated("Back navigation inside the console")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else @Suppress("DEPRECATION") super.onBackPressed()
    }
}
