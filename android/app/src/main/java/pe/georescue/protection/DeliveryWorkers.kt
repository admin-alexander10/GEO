package pe.georescue.protection

import android.Manifest
import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.telephony.SmsManager
import android.util.Base64
import androidx.core.content.ContextCompat
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import android.os.Build
import com.google.android.gms.location.LocationServices
import com.google.android.gms.tasks.Tasks
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.text.Normalizer
import java.util.TimeZone
import java.util.concurrent.TimeUnit

abstract class DeliveryWorker(context: Context, parameters: WorkerParameters) :
    Worker(context, parameters) {
    protected val dao = ProtectionDatabase.get(context).protectionDao()
    protected val clientAlertId: String? = inputData.getString(EXTRA_ALERT_ID)

    protected fun readyAlert(allowClosed: Boolean = false): AutomaticAlertEntity? {
        val id = clientAlertId ?: return null
        val alert = dao.getAlert(id) ?: return null
        return alert.takeIf { allowClosed || it.status == "OPEN" }
    }

    protected fun attempt(alert: AutomaticAlertEntity, channel: String, target: String, type: String): Long =
        dao.addAttempt(
            DeliveryAttemptEntity(
                clientAlertId = alert.clientAlertId,
                channel = channel,
                target = target,
                type = type,
                attemptedAt = System.currentTimeMillis(),
                result = "QUEUED",
            ),
        )

    companion object {
        const val EXTRA_ALERT_ID = "client_alert_id"
        const val EXTRA_TYPE = "message_type"
        const val EXTRA_TARGET = "target"
    }
}

class ApiAlertWorker(context: Context, parameters: WorkerParameters) :
    DeliveryWorker(context, parameters) {
    override fun doWork(): Result {
        val alert = readyAlert() ?: return Result.success()
        if (alert.apiState == "RECIBIDA_POR_SERVIDOR") return Result.success()
        val config = dao.getConfig() ?: return Result.retry()
        if (config.encryptedToken.isBlank()) {
            dao.updateApiState(alert.clientAlertId, "TOKEN_REQUERIDO")
            dao.addAttempt(
                DeliveryAttemptEntity(
                    clientAlertId = alert.clientAlertId,
                    channel = "API",
                    target = "/alertas/despachar/",
                    type = "A",
                    attemptedAt = System.currentTimeMillis(),
                    result = "AUTH_REQUIRED",
                ),
            )
            AlertDelivery.notifyStatusChanged(applicationContext)
            return Result.retry()
        }
        val attemptId = attempt(alert, "API", "/alertas/despachar/", "A")
        return try {
            val token = CredentialVault.decrypt(config.encryptedToken).toString(Charsets.UTF_8)
            val response = RescueApiClient(config.apiBaseUrl).dispatchAlert(token, alert)
            val serverId = response.optInt("alerta_id", 0)
            if (serverId > 0) dao.updateServerAlertId(alert.clientAlertId, serverId)
            dao.updateApiState(alert.clientAlertId, "RECIBIDA_POR_SERVIDOR")
            dao.updateAttempt(attemptId, "SERVER_ACCEPTED", "HTTP 2xx")
            val current = dao.getAlert(alert.clientAlertId)
            if (current?.status == "CANCELLED_BY_USER" && serverId > 0) {
                AlertDelivery.enqueueServerCancellation(applicationContext, alert.clientAlertId, serverId)
            }
            AlertDelivery.notifyStatusChanged(applicationContext)
            Result.success()
        } catch (error: ApiFailure) {
            dao.updateApiState(alert.clientAlertId, "REINTENTO_HTTP_${error.statusCode}")
            dao.updateAttempt(attemptId, "RETRY", "HTTP ${error.statusCode}")
            AlertDelivery.notifyStatusChanged(applicationContext)
            Result.retry()
        } catch (error: Exception) {
            dao.updateApiState(alert.clientAlertId, "REINTENTO_PENDIENTE")
            dao.updateAttempt(attemptId, "RETRY", error.javaClass.simpleName)
            AlertDelivery.notifyStatusChanged(applicationContext)
            Result.retry()
        }
    }
}

class ApiAlertCancellationWorker(context: Context, parameters: WorkerParameters) :
    DeliveryWorker(context, parameters) {
    override fun doWork(): Result {
        val alert = readyAlert(allowClosed = true) ?: return Result.success()
        val serverId = inputData.getInt(EXTRA_SERVER_ALERT_ID, alert.serverAlertId ?: 0)
        if (serverId <= 0) return Result.success()
        val config = dao.getConfig() ?: return Result.retry()
        if (config.encryptedToken.isBlank()) return Result.retry()
        val attemptId = attempt(alert, "API", "/alertas/${serverId}/estado/", "C")
        return try {
            val token = CredentialVault.decrypt(config.encryptedToken).toString(Charsets.UTF_8)
            RescueApiClient(config.apiBaseUrl).cancelAlert(token, serverId)
            dao.updateApiState(alert.clientAlertId, "CANCELADA_EN_SERVIDOR")
            dao.updateAttempt(attemptId, "SERVER_ACCEPTED", "HTTP 2xx")
            AlertDelivery.notifyStatusChanged(applicationContext)
            Result.success()
        } catch (error: ApiFailure) {
            dao.updateApiState(alert.clientAlertId, "CANCELACION_HTTP_${error.statusCode}")
            dao.updateAttempt(attemptId, "RETRY", "HTTP ${error.statusCode}")
            AlertDelivery.notifyStatusChanged(applicationContext)
            Result.retry()
        } catch (error: Exception) {
            dao.updateApiState(alert.clientAlertId, "CANCELACION_PENDIENTE")
            dao.updateAttempt(attemptId, "RETRY", error.javaClass.simpleName)
            AlertDelivery.notifyStatusChanged(applicationContext)
            Result.retry()
        }
    }

    companion object {
        const val EXTRA_SERVER_ALERT_ID = "server_alert_id"
    }
}

class PlatformSmsWorker(context: Context, parameters: WorkerParameters) :
    DeliveryWorker(context, parameters) {
    override fun doWork(): Result {
        val type = inputData.getString(EXTRA_TYPE) ?: "A"
        val alert = readyAlert(allowClosed = type == "C") ?: return Result.success()
        if (
            type != "C" &&
            dao.successfulAttemptCountForType(alert.clientAlertId, "PLATFORM_SMS", type) > 0
        ) return Result.success()
        if (
            type == "C" &&
            dao.successfulAttemptCountForType(alert.clientAlertId, "PLATFORM_SMS", "C") > 0
        ) return Result.success()
        val config = dao.getConfig() ?: return Result.retry()
        if (
            ContextCompat.checkSelfPermission(applicationContext, Manifest.permission.SEND_SMS) !=
            PackageManager.PERMISSION_GRANTED
        ) return Result.retry()
        val target = config.platformPhone
        if (target.isBlank()) {
            dao.updateSmsState(alert.clientAlertId, "NUMERO_PLATAFORMA_REQUERIDO")
            return Result.retry()
        }
        val latitude = alert.latitude
        val longitude = alert.longitude
        val precision = alert.precisionMeters
        val age = alert.currentLocationAgeSeconds()
        if (latitude == null || longitude == null || precision == null || age == null) {
            requestLastLocation(alert)
            return Result.retry()
        }
        if (
            type == "C" &&
            dao.successfulAttemptCount(alert.clientAlertId, "PLATFORM_SMS") == 0
        ) {
            return Result.success()
        }
        val secret = try {
            val encoded = CredentialVault.decrypt(config.encryptedSigningSecret).toString(Charsets.UTF_8)
            Base64.decode(encoded, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        } catch (error: Exception) {
            dao.updateSmsState(alert.clientAlertId, "SECRETO_REQUERIDO")
            return Result.retry()
        }
        val sms = try {
            Gr1Message.sign(
                clientAlertId = alert.clientAlertId,
                type = type.single(),
                latitude = latitude,
                longitude = longitude,
                precisionMeters = precision,
                ageSeconds = age,
                timestampSeconds = System.currentTimeMillis() / 1000L,
                severity = alert.severity,
                secret = secret,
            )
        } finally {
            secret.fill(0)
        }
        val attemptId = attempt(alert, "PLATFORM_SMS", target, type)
        return try {
            val sent = SmsStatusReceiver.pendingIntent(
                applicationContext, alert.clientAlertId, "PLATFORM_SMS", target, type, attemptId, "SENT",
            )
            val delivered = SmsStatusReceiver.pendingIntent(
                applicationContext, alert.clientAlertId, "PLATFORM_SMS", target, type, attemptId, "DELIVERED",
            )
            applicationContext.getSystemService(SmsManager::class.java)
                .sendTextMessage(target, null, sms, sent, delivered)
            dao.updateSmsState(alert.clientAlertId, "SMS_EN_COLA_DEL_DISPOSITIVO")
            AlertDelivery.notifyStatusChanged(applicationContext)
            Result.success()
        } catch (error: Exception) {
            dao.updateAttempt(attemptId, "RETRY", error.javaClass.simpleName)
            dao.updateSmsState(alert.clientAlertId, "REINTENTO_SMS_PENDIENTE")
            Result.retry()
        }
    }

    private fun requestLastLocation(alert: AutomaticAlertEntity) {
        if (
            ContextCompat.checkSelfPermission(applicationContext, Manifest.permission.ACCESS_FINE_LOCATION) !=
            PackageManager.PERMISSION_GRANTED ||
            (Build.VERSION.SDK_INT >= 29 &&
                ContextCompat.checkSelfPermission(
                    applicationContext,
                    Manifest.permission.ACCESS_BACKGROUND_LOCATION,
                ) != PackageManager.PERMISSION_GRANTED)
        ) return
        try {
            val location = Tasks.await(
                LocationServices.getFusedLocationProviderClient(applicationContext).lastLocation,
                4,
                TimeUnit.SECONDS,
            ) ?: return
            val now = System.currentTimeMillis()
            val age = ((now - location.time).coerceAtLeast(0L) / 1000L).coerceAtMost(31536000L)
            if (
                dao.updateLocation(
                    alert.clientAlertId,
                    location.latitude,
                    location.longitude,
                    if (location.hasAccuracy()) location.accuracy.toInt().coerceIn(0, 100000) else 100000,
                    age,
                    now,
                ) == 1
            ) {
                AlertDelivery.enqueueLocationUpdate(applicationContext, alert.clientAlertId)
            }
        } catch (_: Exception) {
            // WorkManager retries the independent SMS task.
        }
    }
}

class TrustedContactsWorker(context: Context, parameters: WorkerParameters) :
    DeliveryWorker(context, parameters) {
    override fun doWork(): Result {
        val alert = readyAlert() ?: return Result.success()
        val latitude = alert.latitude ?: return Result.retry()
        val longitude = alert.longitude ?: return Result.retry()
        if (
            ContextCompat.checkSelfPermission(applicationContext, Manifest.permission.SEND_SMS) !=
            PackageManager.PERMISSION_GRANTED
        ) return Result.retry()
        val contacts = dao.getContacts().filter { it.consentedAt > 0 }
        if (contacts.isEmpty()) return Result.retry()
        var failed = false
        val time = SimpleDateFormat("yyyy-MM-dd HH:mm:ss 'UTC'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(Date(alert.timestampSeconds * 1000L))
        contacts.forEach { contact ->
            if (dao.successfulTargetAttemptCount(alert.clientAlertId, "CONTACT_SMS", contact.phone, "A") > 0) {
                return@forEach
            }
            val name = Normalizer.normalize(contact.name, Normalizer.Form.NFD)
                .replace(Regex("\\p{M}+"), "")
                .filter { it.code in 32..126 }
                .take(20)
                .ifBlank { "Contacto" }
            val lat = "%.5f".format(Locale.US, latitude)
            val lng = "%.5f".format(Locale.US, longitude)
            val text = "GEORESCUE ${alert.clientAlertId}: $name; sismo $lat,$lng; https://maps.google.com/?q=$lat,$lng; $time"
            val attemptId = attempt(alert, "CONTACT_SMS", contact.phone, "A")
            try {
                send(alert, contact.phone, text, attemptId)
            } catch (error: Exception) {
                dao.updateAttempt(attemptId, "RETRY", error.javaClass.simpleName)
                failed = true
            }
        }
        if (failed) return Result.retry()
        return Result.success()
    }

    private fun send(alert: AutomaticAlertEntity, target: String, text: String, attemptId: Long) {
        val manager = applicationContext.getSystemService(SmsManager::class.java)
        require(text.toByteArray(Charsets.US_ASCII).size <= 160)
        manager.sendTextMessage(
            target,
            null,
            text,
            SmsStatusReceiver.pendingIntent(
                applicationContext, alert.clientAlertId, "CONTACT_SMS", target, "A", attemptId, "SENT",
            ),
            SmsStatusReceiver.pendingIntent(
                applicationContext, alert.clientAlertId, "CONTACT_SMS", target, "A", attemptId, "DELIVERED",
            ),
        )
    }
}

class LocationUpdateWorker(context: Context, parameters: WorkerParameters) :
    DeliveryWorker(context, parameters) {
    override fun doWork(): Result {
        val alert = readyAlert() ?: return Result.success()
        val config = dao.getConfig() ?: return Result.retry()
        if (
            ContextCompat.checkSelfPermission(applicationContext, Manifest.permission.SEND_SMS) !=
            PackageManager.PERMISSION_GRANTED
        ) return Result.retry()
        val latitude = alert.latitude ?: return Result.retry()
        val longitude = alert.longitude ?: return Result.retry()
        val precision = alert.precisionMeters ?: return Result.retry()
        val age = alert.currentLocationAgeSeconds() ?: return Result.retry()
        val target = config.platformPhone
        if (target.isBlank()) return Result.retry()
        return try {
            val secretText = CredentialVault.decrypt(config.encryptedSigningSecret).toString(Charsets.UTF_8)
            val secret = Base64.decode(secretText, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
            val message = try {
                Gr1Message.sign(
                    alert.clientAlertId,
                    'U',
                    latitude,
                    longitude,
                    precision,
                    age,
                    System.currentTimeMillis() / 1000L,
                    alert.severity,
                    secret,
                )
            } finally {
                secret.fill(0)
            }
            val attemptId = attempt(alert, "PLATFORM_SMS", target, "U")
            val sent = SmsStatusReceiver.pendingIntent(
                applicationContext, alert.clientAlertId, "PLATFORM_SMS", target, "U", attemptId, "SENT",
            )
            val delivered = SmsStatusReceiver.pendingIntent(
                applicationContext, alert.clientAlertId, "PLATFORM_SMS", target, "U", attemptId, "DELIVERED",
            )
            applicationContext.getSystemService(SmsManager::class.java).sendTextMessage(
                target,
                null,
                message,
                sent,
                delivered,
            )
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }
}

class SmsStatusReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getStringExtra(EXTRA_ALERT_ID) ?: return
        val attemptId = intent.getLongExtra(EXTRA_ATTEMPT_ID, -1L)
        val channel = intent.getStringExtra(EXTRA_CHANNEL) ?: return
        val type = intent.getStringExtra(EXTRA_TYPE) ?: "A"
        val event = intent.getStringExtra(EXTRA_EVENT) ?: return
        val callbackCode = this.resultCode
        val pending = goAsync()
        Thread {
            try {
                val dao = ProtectionDatabase.get(context).protectionDao()
                val attempt = dao.getAttempt(attemptId)
                val alert = dao.getAlert(id)
                val status = if (callbackCode == Activity.RESULT_OK) {
                    if (event.startsWith("DELIVERED")) "SMS_DELIVERED" else "SMS_SENT_TO_NETWORK"
                } else {
                    if (event.startsWith("DELIVERED")) "DELIVERY_NOT_CONFIRMED" else "SEND_FAILED"
                }
                if (attemptId >= 0L) dao.updateAttempt(attemptId, status, "resultCode=$callbackCode")
                if (channel == "PLATFORM_SMS") {
                    dao.updateSmsState(
                        id,
                        when {
                            event.startsWith("DELIVERED") && callbackCode == Activity.RESULT_OK ->
                                "SMS_ENTREGADO_A_${attempt?.target.orEmpty()}"
                            event == "SENT" && callbackCode == Activity.RESULT_OK ->
                                if (alert?.signedSmsState?.startsWith("SMS_ENTREGADO_A_") == true) {
                                    alert.signedSmsState
                                } else {
                                    "SMS_ENVIADO_A_LA_RED_SIN_CONFIRMACION"
                                }
                            event == "SENT" -> "SMS_NO_ENVIADO"
                            else -> "SMS_ENVIADO_A_LA_RED_SIN_CONFIRMACION"
                        },
                    )
                }
                if (
                    event == "SENT" &&
                    callbackCode == Activity.RESULT_OK &&
                    channel == "PLATFORM_SMS" &&
                    type == "A" &&
                    alert?.status == "CANCELLED_BY_USER"
                ) {
                    AlertDelivery.enqueueCancellationSms(context, id)
                }
                if (event == "SENT" && callbackCode != Activity.RESULT_OK) {
                    val input = Data.Builder()
                        .putString(EXTRA_ALERT_ID, id)
                        .putString(EXTRA_TYPE, type)
                        .build()
                    val manager = WorkManager.getInstance(context)
                    val uniqueName = "sms-retry:$channel:$id:$type"
                    if (channel == "PLATFORM_SMS") {
                        manager.enqueueUniqueWork(
                            uniqueName,
                            ExistingWorkPolicy.REPLACE,
                            OneTimeWorkRequestBuilder<PlatformSmsWorker>()
                                .setInputData(input)
                                .setInitialDelay(30, TimeUnit.SECONDS)
                                .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                                .build(),
                        )
                    } else {
                        manager.enqueueUniqueWork(
                            uniqueName,
                            ExistingWorkPolicy.REPLACE,
                            OneTimeWorkRequestBuilder<TrustedContactsWorker>()
                                .setInputData(input)
                                .setInitialDelay(30, TimeUnit.SECONDS)
                                .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                                .build(),
                        )
                    }
                }
                AlertDelivery.notifyStatusChanged(context)
            } finally {
                pending.finish()
            }
        }.start()
    }

    companion object {
        private const val EXTRA_ALERT_ID = "client_alert_id"
        private const val EXTRA_ATTEMPT_ID = "attempt_id"
        private const val EXTRA_CHANNEL = "channel"
        private const val EXTRA_TYPE = "message_type"
        private const val EXTRA_EVENT = "event"

        fun pendingIntent(
            context: Context,
            id: String,
            channel: String,
            target: String,
            type: String,
            attemptId: Long,
            event: String,
        ): PendingIntent {
            val intent = Intent(context, SmsStatusReceiver::class.java).apply {
                data = android.net.Uri.parse(
                    "georescue://sms/${URLEncoder.encode(id, "UTF-8")}/$channel/$type/$event/$attemptId",
                )
                putExtra(EXTRA_ALERT_ID, id)
                putExtra(EXTRA_ATTEMPT_ID, attemptId)
                putExtra(EXTRA_CHANNEL, channel)
                putExtra(EXTRA_TYPE, type)
                putExtra(EXTRA_TARGET, target)
                putExtra(EXTRA_EVENT, event)
            }
            return PendingIntent.getBroadcast(
                context,
                (id + channel + type + event + attemptId).hashCode(),
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }
    }
}
