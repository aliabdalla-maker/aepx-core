package com.softwareequality.aepx

import com.intellij.ide.BrowserUtil
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.project.DumbAware
import java.net.URI

/** Fixed, HTTPS-only destinations. The plugin reads no project files and stores no credentials. */
object AepxLinks {
    const val IDE = "https://ide.softwareequality.com/"
    const val PRICING = "https://www.softwareequality.com/aepx#pricing"

    /** IDE modules a new project can start in (mirrors GET /api/v1/ide-modules). */
    val MODULES = listOf("software", "sound", "music", "film", "animation", "sdk", "social", "multimedia", "media")

    /** Opens the IDE's new-project dialog with a known module preselected. */
    fun newProject(module: String): String = if (module in MODULES) "${IDE}?new=$module" else IDE

    fun isSafe(url: String): Boolean = runCatching {
        val u = URI(url)
        u.scheme == "https" && u.userInfo == null && !u.host.isNullOrEmpty()
    }.getOrDefault(false)
}

abstract class OpenLinkAction(private val url: String) : AnAction(), DumbAware {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT
    override fun actionPerformed(e: AnActionEvent) {
        if (AepxLinks.isSafe(url)) BrowserUtil.browse(url)
    }
}

class OpenIdeAction : OpenLinkAction(AepxLinks.IDE)
class OpenPricingAction : OpenLinkAction(AepxLinks.PRICING)

abstract class NewProjectAction(module: String) : OpenLinkAction(AepxLinks.newProject(module))
class NewSoftwareProject : NewProjectAction("software")
class NewSoundProject : NewProjectAction("sound")
class NewMusicProject : NewProjectAction("music")
class NewFilmProject : NewProjectAction("film")
class NewAnimationProject : NewProjectAction("animation")
class NewSdkProject : NewProjectAction("sdk")
class NewSocialProject : NewProjectAction("social")
class NewMultimediaProject : NewProjectAction("multimedia")
class NewMediaProject : NewProjectAction("media")
