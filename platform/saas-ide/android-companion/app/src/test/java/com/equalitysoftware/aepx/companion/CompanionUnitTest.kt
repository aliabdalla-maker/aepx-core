package com.equalitysoftware.aepx.companion

import com.equalitysoftware.aepx.companion.ads.AdFormat
import com.equalitysoftware.aepx.companion.ads.AdGate
import com.equalitysoftware.aepx.companion.ads.AdRate
import com.equalitysoftware.aepx.companion.billing.Entitlement
import com.equalitysoftware.aepx.companion.billing.Offer
import com.equalitysoftware.aepx.companion.billing.OfferPolicy
import com.equalitysoftware.aepx.companion.ads.AdUnitRegistry
import com.equalitysoftware.aepx.companion.ads.AdsConfig
import com.equalitysoftware.aepx.companion.ads.FrequencyCap
import com.equalitysoftware.aepx.companion.ads.Placement
import com.equalitysoftware.aepx.companion.ads.TestAdUnits
import com.equalitysoftware.aepx.companion.api.IdeJson
import com.equalitysoftware.aepx.companion.api.validateBaseUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class CompanionUnitTest {
    private val pub = "2980680946304710"

    private fun config(enabled: Boolean, vararg units: Triple<String, String?, String?>): String {
        val list = units.joinToString(",") { (id, format, placement) ->
            """{"id":"ca-app-pub-$pub/$id","format":${format?.let { "\"$it\"" } ?: "null"},"placement":${placement?.let { "\"$it\"" } ?: "null"}}"""
        }
        return """{"admob":{"appId":"ca-app-pub-$pub~2617421798","enabled":$enabled,"adUnits":[$list]}}"""
    }

    @Test fun repositoryConfigParsesAndKeepsEveryUnitDisabledUntilFormatsAreSet() {
        val file = File("../../monetization/ads-config.json")
        assertTrue("shared ads-config.json must exist at ${file.absolutePath}", file.exists())
        val cfg = AdsConfig.parse(file.readText())
        assertEquals("ca-app-pub-$pub~2617421798", cfg.appId)
        assertEquals(6, cfg.units.size)
        assertFalse(cfg.enabled)
        val release = AdUnitRegistry(cfg, debug = false)
        val debug = AdUnitRegistry(cfg, debug = true)
        for (p in Placement.entries) {
            assertNull(release.unitFor(p))
            // Debug only shows test ads for placements that are actually mapped; none are yet.
            assertNull(debug.unitFor(p))
        }
        assertFalse(release.mayInitialize(canRequestAds = true))
        assertEquals(6, release.unconfiguredUnits().size)
    }

    @Test fun releaseServesLiveUnitOnlyWhenEnabledAndFormatMatches() {
        val json = config(true, Triple("1032845563", "banner", "runs_list_banner"), Triple("2172884450", "interstitial", null))
        val registry = AdUnitRegistry(AdsConfig.parse(json), debug = false)
        assertEquals("ca-app-pub-$pub/1032845563", registry.unitFor(Placement.RUNS_LIST_BANNER))
        assertNull(registry.unitFor(Placement.RUN_COMPLETED_INTERSTITIAL)) // format set, no placement
        assertTrue(registry.mayInitialize(canRequestAds = true))
        assertFalse(registry.mayInitialize(canRequestAds = false)) // no consent, no SDK init
        val disabled = AdUnitRegistry(AdsConfig.parse(config(false, Triple("1032845563", "banner", "runs_list_banner"))), debug = false)
        assertNull(disabled.unitFor(Placement.RUNS_LIST_BANNER))
    }

    @Test fun debugAlwaysUsesGoogleTestUnits() {
        val json = config(false, Triple("1032845563", "banner", "runs_list_banner"), Triple("2172884450", "interstitial", "run_completed_interstitial"))
        val registry = AdUnitRegistry(AdsConfig.parse(json), debug = true)
        assertEquals(TestAdUnits.forFormat(AdFormat.BANNER), registry.unitFor(Placement.RUNS_LIST_BANNER))
        assertEquals(TestAdUnits.forFormat(AdFormat.INTERSTITIAL), registry.unitFor(Placement.RUN_COMPLETED_INTERSTITIAL))
        for (f in AdFormat.entries) assertTrue(TestAdUnits.forFormat(f).startsWith("ca-app-pub-3940256099942544/"))
    }

    @Test fun malformedConfigurationFailsClosed() {
        val bad = listOf(
            config(true, Triple("1032845563", "banner", "run_completed_interstitial")), // format/placement mismatch
            config(true, Triple("1032845563", "popunder", null)),                       // unknown format
            config(true, Triple("1032845563", "banner", "everywhere")),                 // unknown placement
            config(true, Triple("1032845563", null, null), Triple("1032845563", null, null)), // duplicate unit
            config(true, Triple("1032845563", "banner", "runs_list_banner"), Triple("2172884450", "banner", "runs_list_banner")),
            """{"admob":{"appId":"ca-app-pub-$pub/2617421798","enabled":true,"adUnits":[]}}""",   // unit ID used as app ID
            """{"admob":{"appId":"ca-app-pub-$pub~2617421798","enabled":true,"adUnits":[{"id":"ca-app-pub-1111111111111111/1032845563","format":null,"placement":null}]}}""",
        )
        for (json in bad) assertThrows(IllegalArgumentException::class.java) { AdsConfig.parse(json) }
        assertNull(AdUnitRegistry(null, debug = true).unitFor(Placement.PROJECT_LIST_BANNER))
    }

    @Test fun frequencyCapEnforcesGapAndSessionMaximum() {
        var now = 0L
        val cap = FrequencyCap(minIntervalMs = 1000, maxPerSession = 2) { now }
        assertTrue(cap.tryAcquire())
        now = 500; assertFalse(cap.tryAcquire())
        now = 1500; assertTrue(cap.tryAcquire())
        now = 10_000; assertFalse(cap.tryAcquire())
    }

    @Test fun parsesBackendPayloads() {
        val run = IdeJson.run("""{"id":"r1","status":"awaiting_approval","model_route":"oci",
            "plan":"[{\"agent\":\"architect\",\"action\":\"design\",\"goal\":\"Boundaries\"}]","result":null}""")
        assertEquals("architect · design", run.plan.single().title)
        assertEquals("Boundaries", run.plan.single().detail)
        assertEquals("", run.result)
        val approvals = IdeJson.approvals("""[{"id":"a","server":"knowledge","tool":"search","args_sha256":"abc","state":"pending","requested_by":"u","decided_by":null}]""")
        assertEquals("pending", approvals.single().state)
        assertEquals(listOf("p1"), IdeJson.projects("""[{"id":"p1","name":"x","description":""}]""").map { it.id })
        assertEquals("Retry not permitted", IdeJson.errorDetail("""{"detail":"Retry not permitted"}"""))
        assertNull(IdeJson.errorDetail("<html>"))
        assertEquals("not json", IdeJson.plan("not json").single().title)
    }

    @Test fun apiBaseUrlRequiresHttpsOutsideDebugEmulator() {
        assertEquals("https://ide-api.example.com", validateBaseUrl("https://ide-api.example.com/", debug = false))
        assertThrows(IllegalArgumentException::class.java) { validateBaseUrl("http://ide-api.example.com", debug = false) }
        assertThrows(IllegalArgumentException::class.java) { validateBaseUrl("http://10.0.2.2:8090", debug = false) }
        assertEquals("http://10.0.2.2:8090", validateBaseUrl("http://10.0.2.2:8090", debug = true))
        assertThrows(IllegalArgumentException::class.java) { validateBaseUrl("http://evil.example.com", debug = true) }
    }

    @Test
    fun adRateMatchesWebPolicy() {
        assertTrue((0L until 20L).all { AdRate.allowed(1.0, it) })
        assertEquals(1, (0L until 20L).count { AdRate.allowed(0.05, it) })
        assertEquals(5, (0L until 100L).count { AdRate.allowed(0.05, it) })
        assertFalse(AdRate.allowed(0.0, 0))
        assertFalse(AdRate.allowed(Double.NaN, 0))
        assertFalse(AdRate.allowed(0.05, -1))
    }

    @Test
    fun gateShowsNothingUntilEntitlementKnown() {
        val gate = AdGate()
        assertFalse(gate.tryOpportunity())
        gate.rate = 0.05
        val shown = (0 until 40).count { gate.tryOpportunity() }
        assertEquals(2, shown)
    }

    @Test
    fun entitlementParsingFailsClosed() {
        val account = "0b6f3c2e-8d1a-4f1e-9a51-2a7c9e4d5b60"
        val trial = Entitlement.parse("""{"plan":"trial","ad_rate":1.0,"subscribed":false,"trial_days_left":30,"price":"£4.99/month","account_id":"$account","source":null}""")
        assertEquals(1.0, trial.adRate, 0.0)
        assertTrue(trial.canBuyOnPlay)
        assertEquals("Free trial · 30 days left", trial.label)
        val pro = Entitlement.parse("""{"plan":"pro","ad_rate":0.05,"subscribed":true,"account_id":"$account","source":"google_play"}""")
        assertFalse(pro.canBuyOnPlay)
        assertThrows(IllegalArgumentException::class.java) {
            Entitlement.parse("""{"plan":"vip","ad_rate":0,"account_id":"$account"}""")
        }
        assertThrows(IllegalArgumentException::class.java) {
            Entitlement.parse("""{"plan":"pro","ad_rate":1.5,"account_id":"$account"}""")
        }
        assertThrows(IllegalArgumentException::class.java) {
            Entitlement.parse("""{"plan":"pro","ad_rate":0.05,"account_id":"not-a-uuid"}""")
        }
    }

    @Test
    fun playOfferNeverStacksAStoreTrialOnOurTrial() {
        val offers = listOf(Offer("monthly", "free-trial-7d", "t1"), Offer("monthly", null, "t2"))
        assertEquals("t2", OfferPolicy.choose(offers)?.token)
        assertNull(OfferPolicy.choose(listOf(Offer("monthly", "promo", "t3"))))
    }
}
