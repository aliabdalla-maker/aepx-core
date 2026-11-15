import org.jetbrains.intellij.platform.gradle.IntelliJPlatformType
import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    id("org.jetbrains.kotlin.jvm") version "2.0.21"
    id("org.jetbrains.intellij.platform") version "2.2.1"
}

group = "com.softwareequality.aepx"
version = "0.2.0"

repositories {
    mavenCentral()
    intellijPlatform { defaultRepositories() }
}

dependencies {
    intellijPlatform {
        intellijIdeaCommunity("2024.2.4")
        pluginVerifier()
        testFramework(TestFrameworkType.Platform)
    }
    testImplementation("junit:junit:4.13.2")
}

kotlin { jvmToolchain(21) }

intellijPlatform {
    pluginConfiguration {
        ideaVersion {
            sinceBuild = "242"
            untilBuild = provider { null } // no upper bound; the verifier checks current IDEs
        }
    }
    // Pinned IDE builds: IntelliJ IDEA Community is no longer published separately from 2025.3.
    pluginVerification {
        ides {
            ide(IntelliJPlatformType.IntellijIdeaCommunity, "2024.2.4")
            ide(IntelliJPlatformType.IntellijIdeaCommunity, "2025.1")
        }
    }
    // Signing/publishing read env vars only; never run in CI (owner-only, see README).
    signing {
        certificateChain = providers.environmentVariable("JB_CERTIFICATE_CHAIN")
        privateKey = providers.environmentVariable("JB_PRIVATE_KEY")
        password = providers.environmentVariable("JB_PRIVATE_KEY_PASSWORD")
    }
    publishing { token = providers.environmentVariable("JB_MARKETPLACE_TOKEN") }
}
