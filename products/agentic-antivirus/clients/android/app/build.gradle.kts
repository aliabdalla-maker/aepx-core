plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Debug builds always use Google's published sample app ID; release uses the live ID chosen by
// aav.admobAppId (one of the two supplied app IDs; confirm which is linked to this package in AdMob).
val testAdMobAppId = "ca-app-pub-3940256099942544~3347511713"
val liveAdMobAppId = providers.gradleProperty("aav.admobAppId").orNull ?: "ca-app-pub-2980680946304710~3427805116"

fun env(name: String): String? = providers.environmentVariable(name).orNull?.takeIf { it.isNotBlank() }
fun quoted(v: String) = "\"" + v.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
val uploadKeystore = env("AEPX_UPLOAD_KEYSTORE")
val releaseSigningReady = uploadKeystore != null &&
    listOf("AEPX_UPLOAD_STORE_PASSWORD", "AEPX_UPLOAD_KEY_ALIAS", "AEPX_UPLOAD_KEY_PASSWORD").all { env(it) != null }

val copyAdsConfig = tasks.register<Copy>("copyAdsConfig") {
    from(rootProject.layout.projectDirectory.file("../../monetization/ads-config.json"))
    into(layout.buildDirectory.dir("generated/aavAssets"))
}

android {
    namespace = "com.equalitysoftware.agenticantivirus"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.equalitysoftware.agenticantivirus"
        minSdk = 24
        targetSdk = 35
        versionCode = providers.gradleProperty("aav.versionCode").orNull?.toInt() ?: 1
        versionName = providers.gradleProperty("aav.versionName").orNull ?: "0.1.2"
        buildConfigField("String", "CONSOLE_URL", quoted(providers.gradleProperty("aav.consoleUrl").get()))
        buildConfigField("String", "PLAY_SUBSCRIPTION_ID", quoted(providers.gradleProperty("aav.playSubscriptionId").get()))
    }
    signingConfigs {
        if (releaseSigningReady) create("release") {
            storeFile = file(uploadKeystore!!)
            storePassword = env("AEPX_UPLOAD_STORE_PASSWORD")
            keyAlias = env("AEPX_UPLOAD_KEY_ALIAS")
            keyPassword = env("AEPX_UPLOAD_KEY_PASSWORD")
        }
    }
    buildTypes {
        debug { manifestPlaceholders["admobAppId"] = testAdMobAppId }
        release {
            manifestPlaceholders["admobAppId"] = liveAdMobAppId
            isMinifyEnabled = false
            if (releaseSigningReady) signingConfig = signingConfigs.getByName("release")
        }
    }
    sourceSets["main"].assets.srcDir(layout.buildDirectory.dir("generated/aavAssets"))
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
    testOptions { unitTests.isReturnDefaultValues = true }
}
tasks.named("preBuild") { dependsOn(copyAdsConfig) }

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.webkit:webkit:1.12.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("com.google.android.gms:play-services-ads:23.6.0")
    implementation("com.google.android.ump:user-messaging-platform:3.1.0")
    implementation("com.android.billingclient:billing-ktx:7.1.1")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
