package pe.georescue.protection

import org.json.JSONObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.concurrent.TimeUnit

class RescueApiClient(private val baseUrl: String) {
    fun login(username: String, password: String): String {
        val response = post(
            "/auth/login/",
            null,
            JSONObject()
                .put("usuario", username)
                .put("password", password)
                .put("modo", "familiar"),
        )
        return response.optString("token").takeIf { it.isNotBlank() }
            ?: throw ApiFailure(200, "La API no devolvió un token.")
    }

    fun requestPhoneOtp(token: String, phone: String) {
        post("/telefonos/solicitar-otp", token, JSONObject().put("telefono", phone))
    }

    fun verifyPhoneOtp(token: String, phone: String, code: String) {
        post(
            "/telefonos/verificar-otp",
            token,
            JSONObject().put("telefono", phone).put("codigo", code),
        )
    }

    fun registerDevice(token: String, deviceId: String): String {
        val response = post(
            "/dispositivos/registrar",
            token,
            JSONObject().put("dispositivo_id", deviceId),
        )
        return response.optString("secreto").takeIf { it.isNotBlank() }
            ?: throw ApiFailure(200, "La API no devolvió el secreto de firma.")
    }

    fun dispatchAlert(token: String, alert: AutomaticAlertEntity): JSONObject {
        val payload = JSONObject()
            .put("client_alert_id", alert.clientAlertId)
            .put("tipo_emergencia", "SISMO_INERCIAL")
            .put("nivel_gravedad", alert.severity)
            .put("origen_alerta", "AUTOMATICO_INERCIA")
            .put("estado_confirmacion", "EXPIRADO_INCONSCIENTE")
            .put("timestamp_dispositivo", Instant.ofEpochSecond(alert.timestampSeconds).toString())
        if (alert.latitude != null && alert.longitude != null) {
            payload.put("latitud", alert.latitude)
            payload.put("longitud", alert.longitude)
        }
        if (alert.precisionMeters != null) payload.put("precision_m", alert.precisionMeters)
        alert.currentLocationAgeSeconds()?.let { payload.put("edad_lectura_s", it) }
        return post("/alertas/despachar/", token, payload)
    }

    fun cancelAlert(token: String, serverAlertId: Int) {
        val request = Request.Builder()
            .url(endpointUrl("/alertas/$serverAlertId/estado/"))
            .header("Authorization", "Bearer $token")
            .patch(
                JSONObject().put("estado", "CANCELADA").toString()
                    .toRequestBody("application/json; charset=utf-8".toMediaType()),
            )
            .build()
        OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .build()
            .newCall(request)
            .execute()
            .use { response ->
                if (!response.isSuccessful) {
                    throw ApiFailure(response.code, response.body?.string().orEmpty().take(500))
                }
            }
    }

    private fun post(path: String, token: String?, payload: JSONObject): JSONObject {
        return request("POST", path, token, payload)
    }

    private fun request(method: String, path: String, token: String?, payload: JSONObject): JSONObject {
        val connection = URL(endpointUrl(path)).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 10_000
        connection.readTimeout = 15_000
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        if (!token.isNullOrBlank()) connection.setRequestProperty("Authorization", "Bearer $token")
        try {
            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(payload.toString()) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val responseBody = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                throw ApiFailure(status, responseBody.take(500))
            }
            return if (responseBody.isBlank()) JSONObject() else JSONObject(responseBody)
        } finally {
            connection.disconnect()
        }
    }

    private fun endpointUrl(path: String): String {
        val normalizedBase = baseUrl.trim().trimEnd('/')
        require(normalizedBase.startsWith("https://")) {
            "La URL de la API debe usar HTTPS."
        }
        val apiBase = if (normalizedBase.endsWith("/api/v1")) normalizedBase else "$normalizedBase/api/v1"
        return "$apiBase$path"
    }
}

class ApiFailure(val statusCode: Int, message: String) : Exception(message)
