package pe.georescue.protection

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ApiUrlPolicyTest {
    @Test
    fun httpsIsAcceptedInBothBuildModes() {
        assertTrue(ApiUrlPolicy.isAllowed("https://api.example.test", debugBuild = true))
        assertTrue(ApiUrlPolicy.isAllowed("https://api.example.test", debugBuild = false))
    }

    @Test
    fun httpIsAcceptedOnlyInDebugBuilds() {
        assertTrue(ApiUrlPolicy.isAllowed("http://192.168.1.10:8001", debugBuild = true))
        assertFalse(ApiUrlPolicy.isAllowed("http://192.168.1.10:8001", debugBuild = false))
    }
}
