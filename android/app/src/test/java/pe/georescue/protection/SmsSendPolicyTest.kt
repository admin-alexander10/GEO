package pe.georescue.protection

import org.junit.Assert.assertEquals
import org.junit.Test

class SmsSendPolicyTest {
    @Test
    fun acceptedSmsIsNotSentAgain() {
        assertEquals(
            SmsSendDecision.ALREADY_ACCEPTED,
            SmsSendPolicy.decision(listOf(attempt("SMS_SENT_TO_NETWORK", 1_000L)), 2_000L),
        )
        assertEquals(
            SmsSendDecision.ALREADY_ACCEPTED,
            SmsSendPolicy.decision(listOf(attempt("SMS_DELIVERED", 1_000L)), 2_000L),
        )
    }

    @Test
    fun recentQueuedSmsReservesTheDestinationAgainstConcurrentWorkers() {
        assertEquals(
            SmsSendDecision.ALREADY_IN_PROGRESS,
            SmsSendPolicy.decision(listOf(attempt("QUEUED", 1_000L)), 2_000L),
        )
    }

    @Test
    fun failedOrExpiredAttemptCanBeRetried() {
        assertEquals(
            SmsSendDecision.SEND,
            SmsSendPolicy.decision(listOf(attempt("SEND_FAILED", 1_000L)), 2_000L),
        )
        assertEquals(
            SmsSendDecision.SEND,
            SmsSendPolicy.decision(listOf(attempt("QUEUED", 1_000L)), 122_001L),
        )
    }

    private fun attempt(result: String, attemptedAt: Long) = DeliveryAttemptEntity(
        clientAlertId = "ABCDEFGHJK",
        channel = "PLATFORM_SMS",
        target = "+51999999999",
        type = "A",
        attemptedAt = attemptedAt,
        result = result,
    )
}
