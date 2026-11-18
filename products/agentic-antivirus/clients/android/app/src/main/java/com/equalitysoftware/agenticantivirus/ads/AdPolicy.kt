package com.equalitysoftware.agenticantivirus.ads

import org.json.JSONObject

/**
 * Pure ad policy (JVM-testable). Mirrors monetization/ads-config.json and the control plane:
 *  - trial / unpaid: ad rate 1.0 (every eligible opportunity); paid (GBP 4.99/month): 0.05 (95% fewer)
 *  - only "allowed" placements; never on approval, containment, warning, quarantine, login, payment, audit
 *  - a unit is requested only for a placement whose format it declares; format=null units are never used
 *  - debug builds use Google's sample units; malformed config fails closed (no ads)
 */
enum class AdFormat(val key: String) {
    BANNER("banner"), INTERSTITIAL("interstitial"), NATIVE("native"), APP_OPEN("app_open");
    companion object { fun fromKey(k: String) = entries.firstOrNull { it.key == k } ?: throw IllegalArgumentException("format $k") }
}

enum class Placement(val key: String, val format: AdFormat) {
    DASHBOARD_BANNER("dashboard_banner", AdFormat.BANNER),
    DEVICE_LIST_BANNER("device_list_banner", AdFormat.BANNER),
    INCIDENT_LIST_BANNER("incident_list_banner", AdFormat.BANNER),
    SETTINGS_BANNER("settings_banner", AdFormat.BANNER),
    HELP_BANNER("help_banner", AdFormat.BANNER),
    APP_OPEN("app_open", AdFormat.APP_OPEN),
    LIST_NATIVE("list_native", AdFormat.NATIVE),
    SESSION_END_INTERSTITIAL("session_end_interstitial", AdFormat.INTERSTITIAL);
    companion object { fun fromKey(k: String) = entries.firstOrNull { it.key == k } ?: throw IllegalArgumentException("placement $k") }
}

data class AdUnit(val id: String, val format: AdFormat?, val placement: Placement?)
data class AdsConfig(val enabled: Boolean, val appIds: List<String>, val units: List<AdUnit>, val allowed: Set<String>)

object AdsConfigParser {
    private val APP = Regex("^ca-app-pub-(\\d{16})~\\d{10}$")
    private val UNIT = Regex("^ca-app-pub-(\\d{16})/\\d{10}$")

    fun parse(json: String): AdsConfig {
        val root = JSONObject(json)
        val publisher = root.getString("publisher_id").removePrefix("pub-")
        val admob = root.getJSONObject("admob")
        val apps = admob.getJSONArray("apps")
        val ids = mutableListOf<String>()
        val units = mutableListOf<AdUnit>()
        for (i in 0 until apps.length()) {
            val app = apps.getJSONObject(i)
            val appId = app.getString("app_id")
            require(APP.matchEntire(appId)?.groupValues?.get(1) == publisher) { "app $appId not from publisher" }
            ids += appId
            val arr = app.getJSONArray("units")
            for (j in 0 until arr.length()) {
                val u = arr.getJSONObject(j)
                val id = u.getString("id")
                require(UNIT.matchEntire(id)?.groupValues?.get(1) == publisher) { "unit $id not from publisher" }
                val format = if (u.isNull("format")) null else AdFormat.fromKey(u.getString("format"))
                val placement = if (u.isNull("placement")) null else Placement.fromKey(u.getString("placement"))
                if (placement != null) require(format == placement.format) { "unit $id format mismatch" }
                units += AdUnit(id, format, placement)
            }
        }
        require(units.map { it.id }.toSet().size == units.size) { "duplicate unit" }
        val placed = units.mapNotNull { it.placement }
        require(placed.toSet().size == placed.size) { "placement assigned twice" }
        val allowedArr = root.getJSONObject("placements").getJSONArray("allowed")
        val allowed = (0 until allowedArr.length()).map { allowedArr.getString(it) }.toSet()
        return AdsConfig(admob.getBoolean("enabled"), ids, units, allowed)
    }
}

object TestUnits {
    fun forFormat(f: AdFormat) = when (f) {
        AdFormat.BANNER -> "ca-app-pub-3940256099942544/9214589741"
        AdFormat.INTERSTITIAL -> "ca-app-pub-3940256099942544/1033173712"
        AdFormat.NATIVE -> "ca-app-pub-3940256099942544/2247696110"
        AdFormat.APP_OPEN -> "ca-app-pub-3940256099942544/9257395921"
    }
}

class AdUnitRegistry(private val cfg: AdsConfig?, private val debug: Boolean) {
    fun unitFor(p: Placement): String? {
        val c = cfg ?: return null
        if (p.key !in c.allowed) return null
        val unit = c.units.firstOrNull { it.placement == p && it.format == p.format } ?: return null
        return when {
            debug -> TestUnits.forFormat(p.format)
            c.enabled -> unit.id
            else -> null
        }
    }
}

/** Deterministic pacing, identical to the control plane AdGate and web AdPacer. */
class AdPacer(val rate: Double) {
    init { require(rate in 0.0..1.0) }
    private var n = 0L
    @Synchronized fun next(): Boolean {
        val before = Math.floor(n * rate).toLong()
        n += 1
        return Math.floor(n * rate).toLong() > before
    }
}

/** Which console route the WebView shows decides the native banner placement (null = no ads). */
object RoutePlacement {
    fun forPath(path: String): Placement? = when (path.trimEnd('/').ifEmpty { "/" }.substringBefore('?')) {
        "/", "" -> Placement.DASHBOARD_BANNER
        "/devices" -> Placement.DEVICE_LIST_BANNER
        "/incidents" -> Placement.INCIDENT_LIST_BANNER
        "/settings" -> Placement.SETTINGS_BANNER
        "/help" -> Placement.HELP_BANNER
        else -> null // approvals, incident detail, quarantine, login, billing, audit, privacy...
    }
}
