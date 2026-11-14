package com.equalitysoftware.aepx.companion.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.net.URLEncoder

data class Project(val id: String, val name: String)
data class RunSummary(val id: String, val status: String, val task: String, val modelRoute: String, val attempts: Int)
data class PlanStep(val title: String, val detail: String?)
data class RunDetail(val id: String, val status: String, val modelRoute: String, val plan: List<PlanStep>, val result: String)
data class ToolApproval(val id: String, val server: String, val tool: String, val argsSha256: String, val state: String)
data class AuditEntry(val actor: String, val action: String)

class ApiException(val status: Int, message: String) : Exception(message)

/** Pure JSON mapping for the IDE backend responses (unit-tested on the JVM). */
object IdeJson {
    private fun JSONArray.objects() = (0 until length()).map { getJSONObject(it) }

    fun projects(body: String) = JSONArray(body).objects().map { Project(it.getString("id"), it.getString("name")) }

    fun runs(body: String) = JSONArray(body).objects().map {
        RunSummary(it.getString("id"), it.getString("status"), it.optString("task"), it.optString("model_route"), it.optInt("attempts"))
    }

    fun run(body: String): RunDetail {
        val o = JSONObject(body)
        return RunDetail(o.getString("id"), o.getString("status"), o.optString("model_route"),
            plan(if (o.isNull("plan")) null else o.get("plan")), if (o.isNull("result")) "" else o.optString("result"))
    }

    /** supervisor.plan_steps() is stored as JSON text: [{agent, action, goal}, ...]. */
    fun plan(raw: Any?): List<PlanStep> {
        val array = when (raw) {
            null -> return emptyList()
            is JSONArray -> raw
            is String -> runCatching { JSONArray(raw) }.getOrElse { return if (raw.isBlank()) emptyList() else listOf(PlanStep(raw.trim(), null)) }
            else -> return emptyList()
        }
        return (0 until minOf(array.length(), 50)).map { i ->
            when (val step = array.get(i)) {
                is JSONObject -> {
                    val title = if (step.has("agent")) listOf(step.optString("agent"), step.optString("action")).filter { it.isNotEmpty() }.joinToString(" · ")
                    else step.optString("title", "Step")
                    val detail = listOf("goal", "detail", "description").firstOrNull { step.has(it) }?.let { step.optString(it) }
                    PlanStep(title, detail)
                }
                else -> PlanStep(step.toString(), null)
            }
        }
    }

    fun approvals(body: String) = JSONArray(body).objects().map {
        ToolApproval(it.getString("id"), it.getString("server"), it.getString("tool"), it.getString("args_sha256"), it.getString("state"))
    }

    fun audit(body: String) = JSONArray(body).objects().map { AuditEntry(it.optString("actor"), it.optString("action")) }

    fun errorDetail(body: String?): String? = runCatching { JSONObject(body ?: "").optString("detail").ifEmpty { null } }.getOrNull()
}

/** Validates the configured API base: HTTPS always, plain HTTP only to the emulator host in debug builds. */
fun validateBaseUrl(base: String, debug: Boolean): String {
    val uri = URI(base.trimEnd('/'))
    val emulator = uri.scheme == "http" && uri.host in setOf("10.0.2.2", "localhost", "127.0.0.1")
    require(uri.scheme == "https" || (debug && emulator)) { "API base URL must use HTTPS" }
    require(!uri.host.isNullOrEmpty()) { "API base URL needs a host" }
    return uri.toString()
}

class IdeClient(baseUrl: String, private val tenant: String, private val token: () -> String?, debug: Boolean) {
    private val base = validateBaseUrl(baseUrl, debug)

    private fun seg(value: String) = URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    private suspend fun call(path: String, method: String = "GET"): String = withContext(Dispatchers.IO) {
        val bearer = token() ?: throw ApiException(401, "Sign in first")
        val conn = URI(base + path).toURL().openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 15_000
            conn.readTimeout = 30_000
            conn.instanceFollowRedirects = false
            conn.setRequestProperty("Authorization", "Bearer $bearer")
            conn.setRequestProperty("X-Tenant-ID", tenant)
            conn.setRequestProperty("Accept", "application/json")
            if (method == "POST") { conn.doOutput = true; conn.outputStream.use { } }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() } ?: ""
            if (code !in 200..299) throw ApiException(code, IdeJson.errorDetail(body)?.let { "$code: $it" } ?: "API error $code")
            body
        } finally {
            conn.disconnect()
        }
    }

    suspend fun projects() = IdeJson.projects(call("/api/v1/projects"))
    suspend fun runs(project: String) = IdeJson.runs(call("/api/v1/projects/${seg(project)}/agent-runs"))
    suspend fun run(id: String) = IdeJson.run(call("/api/v1/agent-runs/${seg(id)}"))
    suspend fun audit(id: String) = IdeJson.audit(call("/api/v1/agent-runs/${seg(id)}/audit"))
    suspend fun approvals(id: String) = IdeJson.approvals(call("/api/v1/agent-runs/${seg(id)}/tool-approvals"))
    suspend fun decide(id: String, approved: Boolean) { call("/api/v1/agent-runs/${seg(id)}/decision?approved=$approved", "POST") }
    suspend fun decideTool(id: String, approved: Boolean) { call("/api/v1/tool-approvals/${seg(id)}/decision?approved=$approved", "POST") }
}
