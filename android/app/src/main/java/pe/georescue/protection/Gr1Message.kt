package pe.georescue.protection

import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import java.security.MessageDigest
import java.util.Locale
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

object Gr1Message {
    private const val BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    private val random = SecureRandom()

    fun newClientAlertId(): String {
        val bytes = ByteArray(7)
        random.nextBytes(bytes)
        return base32(bytes).take(10)
    }

    fun clientAlertIdForEvent(eventId: Long, deviceId: String): String {
        require(eventId >= 0L && deviceId.isNotBlank())
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("$deviceId|$eventId".toByteArray(StandardCharsets.US_ASCII))
        return base32(digest).take(10)
    }

    fun sign(
        clientAlertId: String,
        type: Char,
        latitude: Double,
        longitude: Double,
        precisionMeters: Int,
        ageSeconds: Long,
        timestampSeconds: Long,
        severity: Int,
        secret: ByteArray,
    ): String {
        require(clientAlertId.matches(Regex("[A-Z2-7]{10}")))
        require(type in setOf('A', 'M', 'C', 'U'))
        require(latitude in -90.0..90.0 && longitude in -180.0..180.0)
        require(precisionMeters in 0..100000)
        require(ageSeconds in 0..31536000)
        require(timestampSeconds >= 0)
        require(severity in 1..5)
        require(secret.size == 32)
        val canonical = String.format(
            Locale.US,
            "GR1|%s|%s|%.5f|%.5f|%d|%d|%d|%d",
            clientAlertId,
            type,
            latitude,
            longitude,
            precisionMeters,
            ageSeconds,
            timestampSeconds,
            severity,
        ).uppercase(Locale.ROOT)
        val message = "$canonical|${signature(canonical, secret)}"
        require(message.toByteArray(StandardCharsets.US_ASCII).size <= 160)
        return message
    }

    fun signature(canonicalText: String, secret: ByteArray): String {
        require(secret.size == 32)
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret, "HmacSHA256"))
        val digest = mac.doFinal(canonicalText.toByteArray(StandardCharsets.US_ASCII))
        return base32(digest).take(8)
    }

    private fun base32(bytes: ByteArray): String {
        val output = StringBuilder()
        var buffer = 0
        var bits = 0
        for (byte in bytes) {
            buffer = (buffer shl 8) or (byte.toInt() and 0xff)
            bits += 8
            while (bits >= 5) {
                output.append(BASE32[(buffer shr (bits - 5)) and 31])
                bits -= 5
            }
        }
        if (bits > 0) output.append(BASE32[(buffer shl (5 - bits)) and 31])
        return output.toString()
    }
}
