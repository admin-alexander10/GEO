package pe.georescue.protection

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class Gr1MessageTest {
    @Test
    fun contractHmacVectorMatches() {
        val secret = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
            .chunked(2)
            .map { it.toInt(16).toByte() }
            .toByteArray()

        assertEquals(
            "TRGS6IS7",
            Gr1Message.signature(
                "GR1|ABCDEFGHJK|A|-12.04640|-77.04280|5|3|1791500000|4",
                secret,
            ),
        )
        assertEquals(
            "GR1|ABCDEFGHJK|A|-12.04640|-77.04280|5|3|1791500000|4|TRGS6IS7",
            Gr1Message.sign(
                clientAlertId = "ABCDEFGHJK",
                type = 'A',
                latitude = -12.0464,
                longitude = -77.0428,
                precisionMeters = 5,
                ageSeconds = 3,
                timestampSeconds = 1791500000,
                severity = 4,
                secret = secret,
            ),
        )
    }

    @Test
    fun signedAlertUsesContractShapeAndStaysWithinSmsLimit() {
        val message = Gr1Message.sign(
            clientAlertId = "ABCDEFGHJK",
            type = 'A',
            latitude = -12.0464,
            longitude = -77.0428,
            precisionMeters = 5,
            ageSeconds = 3,
            timestampSeconds = 1791500000,
            severity = 4,
            secret = ByteArray(32),
        )

        assertTrue(message.matches(Regex("GR1\\|ABCDEFGHJK\\|A\\|[^|]+\\|[^|]+\\|5\\|3\\|1791500000\\|4\\|[A-Z2-7]{8}")))
        assertTrue(message.toByteArray(Charsets.US_ASCII).size <= 160)
    }

    @Test
    fun clientAlertIdIsTenBase32Characters() {
        repeat(100) {
            assertTrue(Gr1Message.newClientAlertId().matches(Regex("[A-Z2-7]{10}")))
        }
    }

    @Test
    fun clientAlertIdIsStableForTheSameDetectionEvent() {
        val first = Gr1Message.clientAlertIdForEvent(42L, "device-test")

        assertEquals(first, Gr1Message.clientAlertIdForEvent(42L, "device-test"))
        assertTrue(first.matches(Regex("[A-Z2-7]{10}")))
    }
}
