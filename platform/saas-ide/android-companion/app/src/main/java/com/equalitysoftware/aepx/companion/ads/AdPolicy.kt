package com.equalitysoftware.aepx.companion.ads

import org.json.JSONObject

/**
 * Pure ad policy (no Android types) so it is unit-testable on the JVM.
 *
 * Rules:
 *  - A unit is only ever requested for a placement whose format matches the unit's declared format.
 *  - Units with a null format/placement in ads-config.json are never requested.
 *  - Debug builds always substitute Google's published test unit for that format.
 *  - Release builds request live units only when admob.enabled is true and consent allows it.
 *  - Malformed configuration fails closed (IllegalArgumentException -> no ads).
 */
enum class AdFormat(val key: String) {
    BANNER("banner"),
    INTERSTITIAL("interstitial"),
    REWARDED("rewarded"),
    REWARDED_INTERSTITIAL("rewarded_interstitial"),
    NATIVE("native"),
    APP_OPEN("app_open");

    companion object {
        fun fromKey(key: String): AdFormat =
            entries.firstOrNull { it.key == key } ?: throw IllegalArgumentException("Unknown ad format: $key")
    }
}

/** Where the companion app may show ads. Never on approval/decision screens. */
enum class Placement(val key: String, val format: AdFormat) {
    PROJECT_LIST_BANNER("project_list_banner", AdFormat.BANNER),
    RUNS_LIST_BANNER("runs_list_banner", AdFormat.BANNER),
    RUN_COMPLETED_INTERSTITIAL("run_completed_interstitial", AdFormat.INTERSTITIAL),
    APP_OPEN("app_open", AdFormat.APP_OPEN),
    NATIVE_FEED("native_feed", AdFormat.NATIVE);

    companion object {
        fun fromKey(key: String): Placement =
            entries.firstOrNull { it.key == key } ?: throw IllegalArgumentException("Unknown placement: $key")
    }
}

data class AdUnit(val id: String, val format: AdFormat?, val placement: Placement?)

data class AdsConfig(val appId: String, val enabled: Boolean, val units: List<AdUnit>) {
    companion object {
        private val APP_ID = Regex("^ca-app-pub-(\\d{16})~\\d{10}$")
        private val UNIT_ID = Regex("^ca-app-pub-(\\d{16})/\\d{10}$")

        fun parse(json: String): AdsConfig {
            val admob = JSONObject(json).getJSONObject("admob")
            val appId = admob.getString("appId")
            val publisher = APP_ID.matchEntire(appId)?.groupValues?.get(1)
                ?: throw IllegalArgumentException("Invalid AdMob app ID")
            val raw = admob.getJSONArray("adUnits")
            val units = (0 until raw.length()).map { i ->
                val u = raw.getJSONObject(i)
                val id = u.getString("id")
                val unitPublisher = UNIT_ID.matchEntire(id)?.groupValues?.get(1)
                    ?: throw IllegalArgumentException("Invalid ad unit ID at index $i")
                require(unitPublisher == publisher) { "Ad unit $id belongs to another publisher" }
                val format = if (u.isNull("format")) null else AdFormat.fromKey(u.getString("format"))
                val placement = if (u.isNull("placement")) null else Placement.fromKey(u.getString("placement"))
                if (placement != null) {
                    require(format == placement.format) {
                        "Placement ${placement.key} needs a ${placement.format.key} unit, $id is ${format?.key ?: "unset"}"
                    }
                }
                AdUnit(id, format, placement)
            }
            require(units.map { it.id }.toSet().size == units.size) { "Duplicate ad unit IDs" }
            val placed = units.mapNotNull { it.placement }
            require(placed.toSet().size == placed.size) { "A placement is assigned to more than one unit" }
            return AdsConfig(appId, admob.getBoolean("enabled"), units)
        }
    }
}

/** Google's published sample ad units: https://developers.google.com/admob/android/test-ads */
object TestAdUnits {
    const val APP_ID = "ca-app-pub-3940256099942544~3347511713"
    fun forFormat(format: AdFormat): String = when (format) {
        AdFormat.BANNER -> "ca-app-pub-3940256099942544/9214589741"
        AdFormat.INTERSTITIAL -> "ca-app-pub-3940256099942544/1033173712"
        AdFormat.REWARDED -> "ca-app-pub-3940256099942544/5224354917"
        AdFormat.REWARDED_INTERSTITIAL -> "ca-app-pub-3940256099942544/5354046379"
        AdFormat.NATIVE -> "ca-app-pub-3940256099942544/2247696110"
        AdFormat.APP_OPEN -> "ca-app-pub-3940256099942544/9257395921"
    }
}

class AdUnitRegistry(private val config: AdsConfig?, private val debug: Boolean) {
    /** Ad unit ID to request for [placement], or null when that placement must stay empty. */
    fun unitFor(placement: Placement): String? {
        val cfg = config ?: return null
        val unit = cfg.units.firstOrNull { it.placement == placement && it.format == placement.format } ?: return null
        return when {
            debug -> TestAdUnits.forFormat(placement.format)
            cfg.enabled -> unit.id
            else -> null
        }
    }

    /** MobileAds may be initialised only with consent and when some placement can serve. */
    fun mayInitialize(canRequestAds: Boolean): Boolean =
        canRequestAds && Placement.entries.any { unitFor(it) != null }

    /** Units still waiting for a format from the AdMob console (shown on the About screen). */
    fun unconfiguredUnits(): List<String> = config?.units?.filter { it.format == null }?.map { it.id } ?: emptyList()
}

/** Caps full-screen ads: a minimum gap and a per-session maximum. */
class FrequencyCap(private val minIntervalMs: Long, private val maxPerSession: Int, private val now: () -> Long) {
    private var shown = 0
    private var last: Long? = null

    fun tryAcquire(): Boolean {
        val t = now()
        val previous = last
        if (shown >= maxPerSession || (previous != null && t - previous < minIntervalMs)) return false
        shown += 1
        last = t
        return true
    }
}
