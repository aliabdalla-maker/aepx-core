package com.softwareequality.aepx

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AepxLinksTest {
    @Test
    fun onlyHttpsLinks() {
        assertTrue(AepxLinks.isSafe(AepxLinks.IDE))
        assertTrue(AepxLinks.isSafe(AepxLinks.PRICING))
        listOf("http://ide.softwareequality.com", "file:///etc/passwd", "https://u:p@x.org", "nonsense")
            .forEach { assertFalse(it, AepxLinks.isSafe(it)) }
    }
}
