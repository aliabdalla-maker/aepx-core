package com.equalitysoftware.aepx.companion

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.equalitysoftware.aepx.companion.ads.AdUnitRegistry
import com.equalitysoftware.aepx.companion.ads.AdsConfig
import com.equalitysoftware.aepx.companion.ads.AdsRuntime
import com.equalitysoftware.aepx.companion.ads.BannerSlot
import com.equalitysoftware.aepx.companion.ads.NativeFeedSlot
import com.equalitysoftware.aepx.companion.ads.Placement
import com.equalitysoftware.aepx.companion.api.AuditEntry
import com.equalitysoftware.aepx.companion.api.IdeClient
import com.equalitysoftware.aepx.companion.api.Project
import com.equalitysoftware.aepx.companion.api.RunDetail
import com.equalitysoftware.aepx.companion.api.RunSummary
import com.equalitysoftware.aepx.companion.api.ToolApproval
import kotlinx.coroutines.launch
import net.openid.appauth.AuthorizationException
import net.openid.appauth.AuthorizationRequest
import net.openid.appauth.AuthorizationResponse
import net.openid.appauth.AuthorizationService
import net.openid.appauth.AuthorizationServiceConfiguration
import net.openid.appauth.ResponseTypeValues

private sealed interface Screen {
    data object SignIn : Screen
    data object Projects : Screen
    data class Runs(val project: Project) : Screen
    data class Run(val project: Project, val runId: String) : Screen
    data object About : Screen
}

private class PendingConfirm(val text: String, val action: suspend () -> Unit)

private val TERMINAL = setOf("succeeded", "failed", "cancelled", "rejected")
private const val REDIRECT = "com.equalitysoftware.aepx.companion:/oauth2redirect"

class MainActivity : ComponentActivity() {
    private lateinit var authService: AuthorizationService

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        authService = AuthorizationService(this)
        // Fail closed: a missing or malformed ads-config.json means no ads at all.
        val config = runCatching {
            assets.open("ads-config.json").bufferedReader().use { AdsConfig.parse(it.readText()) }
        }.getOrNull()
        val registry = AdUnitRegistry(config, BuildConfig.DEBUG)
        val ads = AdsRuntime(this, registry).also { it.start() }
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(Modifier.fillMaxSize()) { App(authService, ads, registry) }
            }
        }
    }

    override fun onDestroy() {
        authService.dispose()
        super.onDestroy()
    }
}

@Composable
private fun App(authService: AuthorizationService, ads: AdsRuntime?, registry: AdUnitRegistry) {
    var token by remember { mutableStateOf<String?>(null) } // memory only; never persisted
    var screen by remember { mutableStateOf<Screen>(Screen.SignIn) }
    var message by remember { mutableStateOf("") }
    val client = remember {
        runCatching { IdeClient(BuildConfig.API_BASE_URL, BuildConfig.TENANT, { token }, BuildConfig.DEBUG) }.getOrNull()
    }
    if (client == null && message.isEmpty()) message = "API base URL must use HTTPS"

    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val data = result.data
        val response = data?.let { AuthorizationResponse.fromIntent(it) }
        if (response == null) {
            message = data?.let { AuthorizationException.fromIntent(it)?.errorDescription } ?: "Sign-in cancelled"
            return@rememberLauncherForActivityResult
        }
        authService.performTokenRequest(response.createTokenExchangeRequest()) { tokens, error ->
            val access = tokens?.accessToken
            if (access != null) {
                token = access; screen = Screen.Projects; message = ""
            } else {
                message = error?.errorDescription ?: "Token exchange failed"
            }
        }
    }

    val signIn: () -> Unit = {
        AuthorizationServiceConfiguration.fetchFromIssuer(Uri.parse(BuildConfig.OIDC_ISSUER)) { cfg, error ->
            if (cfg == null) {
                message = error?.errorDescription ?: "OIDC discovery failed"
            } else {
                // AppAuth adds PKCE (S256) automatically.
                val request = AuthorizationRequest.Builder(cfg, BuildConfig.OIDC_CLIENT_ID, ResponseTypeValues.CODE, Uri.parse(REDIRECT))
                    .setScopes("openid", "profile").build()
                launcher.launch(authService.getAuthorizationRequestIntent(request))
            }
        }
    }
    val report: (String) -> Unit = { message = it }

    Column(Modifier.fillMaxSize().systemBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("AEP-X", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            TextButton(onClick = { screen = Screen.About }) { Text("About") }
            if (token != null) TextButton(onClick = { token = null; screen = Screen.SignIn }) { Text("Sign out") }
        }
        if (message.isNotEmpty()) Text(message, Modifier.padding(horizontal = 12.dp), color = MaterialTheme.colorScheme.error)
        Column(Modifier.weight(1f)) {
            when (val s = screen) {
                Screen.SignIn -> SignIn(enabled = client != null, onSignIn = signIn)
                Screen.Projects -> ProjectsScreen(client, ads, report) { screen = Screen.Runs(it) }
                is Screen.Runs -> {
                    BackHandler { screen = Screen.Projects }
                    RunsScreen(client, s.project, ads, report) { screen = Screen.Run(s.project, it) }
                }
                is Screen.Run -> RunScreen(client, s.runId, report) { finalStatus ->
                    if (finalStatus in TERMINAL) ads?.onLeftCompletedRun()
                    screen = Screen.Runs(s.project)
                }
                Screen.About -> {
                    BackHandler { screen = if (token == null) Screen.SignIn else Screen.Projects }
                    AboutScreen(ads, registry)
                }
            }
        }
    }
}

@Composable
private fun SignIn(enabled: Boolean, onSignIn: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
        Text("Governed agentic development", style = MaterialTheme.typography.headlineSmall)
        Text("Review plans and approve agent tool calls from your phone. Every decision is audited.")
        Spacer(Modifier.padding(8.dp))
        Button(onClick = onSignIn, enabled = enabled) { Text("Sign in with your organisation") }
    }
}

@Composable
private fun ProjectsScreen(client: IdeClient?, ads: AdsRuntime?, onError: (String) -> Unit, open: (Project) -> Unit) {
    var projects by remember { mutableStateOf<List<Project>>(emptyList()) }
    LaunchedEffect(client) {
        runCatching { client?.projects() ?: emptyList() }
            .onSuccess { projects = it }.onFailure { onError(it.message ?: "Error") }
    }
    Column(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.weight(1f)) {
            item { Text("Projects", Modifier.padding(12.dp), style = MaterialTheme.typography.titleMedium) }
            items(projects, key = { it.id }) { p ->
                Text(p.name, Modifier.fillMaxWidth().clickable { open(p) }.padding(16.dp))
                HorizontalDivider()
            }
            item { NativeFeedSlot(ads, Modifier.padding(12.dp)) }
        }
        BannerSlot(ads, Placement.PROJECT_LIST_BANNER)
    }
}

@Composable
private fun RunsScreen(client: IdeClient?, project: Project, ads: AdsRuntime?, onError: (String) -> Unit, open: (String) -> Unit) {
    var runs by remember { mutableStateOf<List<RunSummary>>(emptyList()) }
    LaunchedEffect(project.id) {
        runCatching { client?.runs(project.id) ?: emptyList() }
            .onSuccess { runs = it }.onFailure { onError(it.message ?: "Error") }
    }
    Column(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.weight(1f)) {
            item { Text(project.name, Modifier.padding(12.dp), style = MaterialTheme.typography.titleMedium) }
            items(runs, key = { it.id }) { r ->
                Column(Modifier.fillMaxWidth().clickable { open(r.id) }.padding(16.dp)) {
                    Text(r.status.replace('_', ' '), color = MaterialTheme.colorScheme.primary)
                    Text(r.task, maxLines = 2)
                }
                HorizontalDivider()
            }
        }
        BannerSlot(ads, Placement.RUNS_LIST_BANNER)
    }
}

/** Approval surface: intentionally ad-free (accidental-click and decision-integrity policy). */
@Composable
private fun RunScreen(client: IdeClient?, runId: String, onError: (String) -> Unit, back: (String) -> Unit) {
    var run by remember { mutableStateOf<RunDetail?>(null) }
    var approvals by remember { mutableStateOf<List<ToolApproval>>(emptyList()) }
    var audit by remember { mutableStateOf<List<AuditEntry>>(emptyList()) }
    var confirm by remember { mutableStateOf<PendingConfirm?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    fun ask(text: String, action: suspend () -> Unit) { confirm = PendingConfirm(text, action) }

    BackHandler { back(run?.status ?: "") }
    LaunchedEffect(runId, reload) {
        val c = client ?: return@LaunchedEffect
        runCatching { Triple(c.run(runId), c.approvals(runId), c.audit(runId)) }
            .onSuccess { (r, a, log) -> run = r; approvals = a; audit = log }
            .onFailure { onError(it.message ?: "Error") }
    }
    val r = run ?: return
    LazyColumn(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item { Text("${r.status.replace('_', ' ')} · ${r.modelRoute}", color = MaterialTheme.colorScheme.primary) }
        item { Text("Plan", style = MaterialTheme.typography.titleSmall) }
        items(r.plan) { step -> Text("• " + step.title + (step.detail?.let { " — $it" } ?: "")) }
        if (r.result.isNotEmpty()) item { Card { Text(r.result, Modifier.padding(12.dp)) } }
        if (r.status == "awaiting_approval") item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { ask("Approve this plan? Approval is audited.") { client?.decide(runId, true) } }) { Text("Approve plan") }
                OutlinedButton(onClick = { ask("Reject this plan?") { client?.decide(runId, false) } }) { Text("Reject") }
            }
        }
        item { Text("Tool approvals", style = MaterialTheme.typography.titleSmall) }
        items(approvals, key = { it.id }) { a ->
            Card {
                Column(Modifier.padding(12.dp)) {
                    Text("${a.server}.${a.tool} · ${a.state}")
                    Text("args sha256 ${a.argsSha256.take(16)}…", style = MaterialTheme.typography.bodySmall)
                    if (a.state == "pending") Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { ask("Approve ${a.server}.${a.tool} (single use, audited)?") { client?.decideTool(a.id, true) } }) { Text("Approve") }
                        OutlinedButton(onClick = { ask("Reject ${a.server}.${a.tool}?") { client?.decideTool(a.id, false) } }) { Text("Reject") }
                    }
                }
            }
        }
        item { Text("Audit trail", style = MaterialTheme.typography.titleSmall) }
        items(audit) { e -> Text("${e.action} — ${e.actor}", style = MaterialTheme.typography.bodySmall) }
    }
    val pending = confirm
    if (pending != null) {
        AlertDialog(
            onDismissRequest = { confirm = null },
            text = { Text(pending.text) },
            confirmButton = {
                TextButton(onClick = {
                    confirm = null
                    scope.launch {
                        runCatching { pending.action() }
                            .onSuccess { reload += 1 }
                            .onFailure { onError(it.message ?: "Error") }
                    }
                }) { Text("Confirm") }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun AboutScreen(ads: AdsRuntime?, registry: AdUnitRegistry) {
    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("AEP-X companion ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.titleMedium)
        Text(if (BuildConfig.DEBUG) "Debug build: Google test ads only." else "Release build.")
        val pending = registry.unconfiguredUnits()
        if (pending.isNotEmpty()) Text("${pending.size} ad units await a format from the AdMob console and stay disabled.")
        if (ads?.privacyOptionsRequired == true) Button(onClick = { ads.showPrivacyOptions() }) { Text("Privacy options") }
    }
}
