import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Google's published sample IDs: debug builds never request the real AdMob account.
val testAdMobAppId = "ca-app-pub-3940256099942544~3347511713"
val liveAdMobAppId = "ca-app-pub-2980680946304710~2617421798"

fun prop(name: String) = providers.gradleProperty(name).get()
fun quoted(value: String) = "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

/** Packages monetization/ads-config.json (single source of truth shared with the web IDE) as an asset. */
abstract class CopyAdsConfig : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val source: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun copy() {
        val out = outputDir.get().asFile
        out.mkdirs()
        source.get().asFile.copyTo(out.resolve("ads-config.json"), overwrite = true)
    }
}

val copyAdsConfig = tasks.register<CopyAdsConfig>("copyAdsConfig") {
    source.set(rootProject.layout.projectDirectory.file("../monetization/ads-config.json"))
}

android {
    namespace = "com.equalitysoftware.aepx.companion"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.equalitysoftware.aepx.companion"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "API_BASE_URL", quoted(prop("aepx.apiBaseUrl")))
        buildConfigField("String", "TENANT", quoted(prop("aepx.tenant")))
        buildConfigField("String", "OIDC_ISSUER", quoted(prop("aepx.oidcIssuer")))
        buildConfigField("String", "OIDC_CLIENT_ID", quoted(prop("aepx.oidcClientId")))
        manifestPlaceholders["appAuthRedirectScheme"] = "com.equalitysoftware.aepx.companion"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            manifestPlaceholders["admobAppId"] = testAdMobAppId
            manifestPlaceholders["usesCleartext"] = "true" // emulator -> http://10.0.2.2 only
        }
        release {
            manifestPlaceholders["admobAppId"] = liveAdMobAppId
            manifestPlaceholders["usesCleartext"] = "false"
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions { unitTests.isReturnDefaultValues = true }
}

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(copyAdsConfig, CopyAdsConfig::outputDir)
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("com.google.android.gms:play-services-ads:23.6.0")
    implementation("com.google.android.ump:user-messaging-platform:3.1.0")
    implementation("net.openid:appauth:0.11.1")

    testImplementation("junit:junit:4.13.2")
    // Real org.json for JVM unit tests (android.jar only ships stubs).
    testImplementation("org.json:json:20240303")
}
