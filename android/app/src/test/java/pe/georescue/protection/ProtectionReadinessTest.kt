package pe.georescue.protection

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtectionReadinessTest {
    @Test
    fun protectionIsNotReadyWithoutBackgroundLocationOrSetupItems() {
        val requirements = ProtectionRequirements(
            fineLocation = true,
            backgroundLocation = false,
            sms = true,
            batteryUnrestricted = true,
            platformPhone = true,
            signingSecret = true,
            verifiedPhone = true,
            consentedContact = true,
            apiToken = true,
            apiUrlConfigured = true,
            notifications = true,
            fullScreenIntent = true,
        )

        assertFalse(ProtectionReadiness.isReady(requirements))
        assertTrue(ProtectionReadiness.missingSteps(requirements).any { it.contains("segundo plano") })
    }

    @Test
    fun protectionIsReadyOnlyWhenEveryRequirementIsPresent() {
        val requirements = ProtectionRequirements(
            fineLocation = true,
            backgroundLocation = true,
            sms = true,
            batteryUnrestricted = true,
            platformPhone = true,
            signingSecret = true,
            verifiedPhone = true,
            consentedContact = true,
            apiToken = true,
            apiUrlConfigured = true,
            notifications = true,
            fullScreenIntent = true,
        )

        assertTrue(ProtectionReadiness.isReady(requirements))
        assertTrue(ProtectionReadiness.missingSteps(requirements).isEmpty())
    }

    @Test
    fun deliveryLabelsOnlyClaimStatesReportedBySmsCallbacks() {
        assertEquals(
            "SMS enviado a la red (sin confirmación) a +51999999999.",
            ProtectionReadiness.deliveryLabel("SMS_SENT_TO_NETWORK", "+51999999999"),
        )
        assertEquals("SMS entregado a +51999999999.", ProtectionReadiness.deliveryLabel("SMS_DELIVERED", "+51999999999"))
        assertEquals("SMS no enviado a +51999999999.", ProtectionReadiness.deliveryLabel("SEND_FAILED", "+51999999999"))
        assertEquals(
            "Entrega no confirmada a +51999999999.",
            ProtectionReadiness.deliveryLabel("DELIVERY_NOT_CONFIRMED", "+51999999999"),
        )
    }
}
