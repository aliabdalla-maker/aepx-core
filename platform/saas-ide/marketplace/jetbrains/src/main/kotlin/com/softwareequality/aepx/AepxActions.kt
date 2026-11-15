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
