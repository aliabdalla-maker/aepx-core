package com.equalitysoftware.agenticantivirus

import com.equalitysoftware.agenticantivirus.ads.AdFormat
import com.equalitysoftware.agenticantivirus.ads.AdPacer
import com.equalitysoftware.agenticantivirus.ads.AdUnitRegistry
import com.equalitysoftware.agenticantivirus.ads.AdsConfigParser
import com.equalitysoftware.agenticantivirus.ads.Placement
import com.equalitysoftware.agenticantivirus.ads.RoutePlacement
import com.equalitysoftware.agenticantivirus.ads.TestUnits
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test
import java.io.File

class AdPolicyTest {
    private val shipped = File("../../../monetization/ads-config.json").readText()

    @Test fun shippedConfigHasBothAppsAndAllElevenUnitsAndServesNothingUntilFormatsAreSet() {
        val cfg = AdsConfigParser.parse(shipped)
        assertEquals(listOf("ca-app-pub-2980680946304710~3427805116", "ca-app-pub-2980680946304710~2617421798"), cfg.appIds)
        assertEquals(11, cfg.units.size)
        val release = AdUnitRegistry(cfg, debug = false)
        Placement.entries.forEach { assertNull(release.unitFor(it)) }
    }

    @Test fun configuredUnitServesOnlyItsPlacementAndDebugUsesTestIds() {
        val json = shipped.replace("\"id\": \"ca-app-pub-2980680946304710/6357220784\", \"format\": null, \"placement\": null",
            "\"id\": \"ca-app-pub-2980680946304710/6357220784\", \"format\": \"banner\", \"placement\": \"dashboard_banner\"")
            .replace("\"enabled\": false,\n    \"apps\"", "\"enabled\": true,\n    \"apps\"")
        val cfg = AdsConfigParser.parse(json)
        assertEquals("ca-app-pub-2980680946304710/6357220784", AdUnitRegistry(cfg, false).unitFor(Placement.DASHBOARD_BANNER))
        assertEquals(TestUnits.forFormat(AdFormat.BANNER), AdUnitRegistry(cfg, true).unitFor(Placement.DASHBOARD_BANNER))
        assertNull(AdUnitRegistry(cfg, false).unitFor(Placement.HELP_BANNER))
    }

    @Test fun wrongPublisherOrFormatFailsClosed() {
        assertThrows(IllegalArgumentException::class.java) {
            AdsConfigParser.parse(shipped.replace("ca-app-pub-2980680946304710/2665387781", "ca-app-pub-1111111111111111/2665387781"))
        }
        assertThrows(IllegalArgumentException::class.java) {
            AdsConfigParser.parse(shipped.replace("\"id\": \"ca-app-pub-2980680946304710/7811958596\", \"format\": null, \"placement\": null",
                "\"id\": \"ca-app-pub-2980680946304710/7811958596\", \"format\": \"interstitial\", \"placement\": \"dashboard_banner\""))
        }
    }

    @Test fun pacingIsExactlyFullOrFivePercent() {
        val full = AdPacer(1.0); val paid = AdPacer(0.05)
        assertEquals(1000, (1..1000).count { full.next() })
        assertEquals(50, (1..1000).count { paid.next() })
    }

    @Test fun noAdsOnDecisionOrSensitiveScreens() {
        assertEquals(Placement.DASHBOARD_BANNER, RoutePlacement.forPath("/"))
        listOf("/approvals/", "/incident/?id=1", "/quarantine/", "/login/", "/billing/", "/audit/").forEach {
            assertNull(it, RoutePlacement.forPath(it))
        }
    }
}
