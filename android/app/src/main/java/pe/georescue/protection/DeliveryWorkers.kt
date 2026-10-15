package pe.georescue.protection

import android.Manifest
import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.telephony.SmsManager
import android.util.Base64
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.ForegroundInfo
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
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

    override fun getForegroundInfo(): ForegroundInfo {
        val manager = applicationContext.getSystemService(NotificationManager::class.java)
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            manager.getNotificationChannel("protection") == null
        ) {
            manager.createNotificationChannel(
                NotificationChannel(
                    "protection",
                    "Protección sísmica",
                    NotificationManager.IMPORTANCE_LOW,
                ),
            )
        }
        val notification = NotificationCompat.Builder(applicationContext, "protection")
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setContentTitle("Protección sísmica activa")
            .setContentText("Vigilancia local del acelerómetro activa.")
            .setOngoing(true)
            .build()
        return ForegroundInfo(103, notification)
    }

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

enum class SmsDispatchOutcome {
    QUEUED,
    ALREADY_ACCEPTED,
    ALREADY_IN_PROGRESS,
    RETRY,
}

object SmsDelivery {
    fun sendPlatform(
        context: Context,
        dao: ProtectionDao,
        alert: AutomaticAlertEntity,
        type: String,
    ): SmsDispatchOutcome {
        if (
            ContextCompat.checkSelfPermission(context, Manifest.permission.SEND_SMS) !=
            PackageManager.PERMISSION_GRANTED
        ) return SmsDispatchOutcome.RETRY
        val config = dao.getConfig() ?: return SmsDispatchOutcome.RETRY
        val target = config.platformPhone
        if (target.isBlank()) {
            dao.updateSmsState(alert.clientAlertId, "NUMERO_PLATAFORMA_REQUERIDO")
            return SmsDispatchOutcome.RETRY
        }
        val latitude = alert.latitude
        val longitude = alert.longitude
        val precision = alert.precisionMeters
        val age = alert.currentLocationAgeSeconds()
        if (latitude == null || longitude == null || precision == null || age == null) {
            return SmsDispatchOutcome.RETRY
        }
        if (
            type == "C" &&
            dao.successfulAttemptCountForType(alert.clientAlertId, "PLATFORM_SMS", "A") == 0
        ) return SmsDispatchOutcome.ALREADY_ACCEPTED
        val secret = try {
            val encoded = CredentialVault.decrypt(config.encryptedSigningSecret).toString(Charsets.UTF_8)
            Base64.decode(encoded, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        } catch (error: Exception) {
            dao.updateSmsState(alert.clientAlertId, "SECRETO_REQUERIDO")
            return SmsDispatchOutcome.RETRY
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
        } catch (_: Exception) {
            dao.updateSmsState(alert.clientAlertId, "FIRMA_SMS_PENDIENTE")
            return SmsDispatchOutcome.RETRY
        } finally {
            secret.fill(0)
        }
        val now = System.currentTimeMillis()
        val attemptId = dao.reserveSmsAttempt(
            DeliveryAttemptEntity(
                clientAlertId = alert.clientAlertId,
                channel = "PLATFORM_SMS",
                target = target,
                type = type,
                attemptedAt = now,
                result = "QUEUED",
                detail = "triggerAtMs=${alert.timestampSeconds * 1000L}",
            ),
            now,
        ) ?: return when (
            SmsSendPolicy.decision(
                dao.getSmsAttempts(alert.clientAlertId, "PLATFORM_SMS", target, type),
                System.currentTimeMillis(),
            )
        ) {
            SmsSendDecision.ALREADY_ACCEPTED -> SmsDispatchOutcome.ALREADY_ACCEPTED
            SmsSendDecision.ALREADY_IN_PROGRESS -> SmsDispatchOutcome.ALREADY_IN_PROGRESS
            SmsSendDecision.SEND -> SmsDispatchOutcome.RETRY
        }
        return try {
            val sent = SmsStatusReceiver.pendingIntent(
                context, alert.clientAlertId, "PLATFORM_SMS", target, type, attemptId, "SENT",
            )
            val delivered = SmsStatusReceiver.pendingIntent(
                context, alert.clientAlertId, "PLATFORM_SMS", target, type, attemptId, "DELIVERED",
            )
            context.getSystemService(SmsManager::class.java)
                .sendTextMessage(target, null, sms, sent, delivered)
            dao.updateSmsState(alert.clientAlertId, "SMS_EN_COLA_DEL_DISPOSITIVO")
            AlertDelivery.notifyStatusChanged(context)
            SmsDispatchOutcome.QUEUED
        } catch (error: Exception) {
            dao.updateAttempt(attemptId, "RETRY", error.javaClass.simpleName)
            dao.updateSmsState(alert.clientAlertId, "REINTENTO_SMS_PENDIENTE")
            SmsDispatchOutcome.RETRY
        }
    }

    fun sendTrustedContacts(context: Context, dao: ProtectionDao, alert: AutomaticAlertEntity): Boolean {
        val latitude = alert.latitude ?: return false
        val longitude = alert.longitude ?: return false
        if (
            ContextCompat.checkSelfPermission(context, Manifest.permission.SEND_SMS) !=
            PackageManager.PERMISSION_GRANTED
        ) return false
        val contacts = dao.getContacts().filter { it.consentedAt > 0 }
        if (contacts.isEmpty()) return false
        var retry = false
        val time = SimpleDateFormat("yyyy-MM-dd HH:mm:ss 'UTC'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(Date(alert.timestampSeconds * 1000L))
        contacts.forEach { contact ->
            val existing = dao.getSmsAttempts(
                alert.clientAlertId,
                "CONTACT_SMS",
                contact.phone,
                "A",
            )
            when (SmsSendPolicy.decision(existing, System.currentTimeMillis())) {
                SmsSendDecision.ALREADY_ACCEPTED -> return@forEach
                SmsSendDecision.ALREADY_IN_PROGRESS -> {
                    retry = true
                    return@forEach
                }
                SmsSendDecision.SEND -> Unit
            }
            val name = Normalizer.normalize(contact.name, Normalizer.Form.NFD)
                .replace(Regex("\\p{M}+"), "")
                .filter { it.code in 32..126 }
                .take(20)
                .ifBlank { "Contacto" }
            val lat = "%.5f".format(Locale.US, latitude)
            val lng = "%.5f".format(Locale.US, longitude)
            val text = "GEORESCUE ${alert.clientAlertId}: $name; sismo $lat,$lng; https://maps.google.com/?q=$lat,$lng; $time"
            val now = System.currentTimeMillis()
            val attemptId = dao.reserveSmsAttempt(
                DeliveryAttemptEntity(
                    clientAlertId = alert.clientAlertId,
                    channel = "CONTACT_SMS",
                    target = contact.phone,
                    type = "A",
                    attemptedAt = now,
                    result = "QUEUED",
                    detail = "triggerAtMs=${alert.timestampSeconds * 1000L}",
                ),
                now,
            )
            if (attemptId == null) {
                retry = true
                return@forEach
            }
            try {
                require(text.toByteArray(Charsets.US_ASCII).size <= 160)
                context.getSystemService(SmsManager::class.java).sendTextMessage(
                    contact.phone,
                    null,
                    text,
                    SmsStatusReceiver.pendingIntent(
                        context, alert.clientAlertId, "CONTACT_SMS", contact.phone, "A", attemptId, "SENT",
                    ),
                    SmsStatusReceiver.pendingIntent(
                        context, alert.clientAlertId, "CONTACT_SMS", contact.phone, "A", attemptId, "DELIVERED",
                    ),
                )
            } catch (error: Exception) {
                dao.updateAttempt(attemptId, "RETRY", error.javaClass.simpleName)
                retry = true
            }
        }
        return !retry
    }
}

class PlatformSmsWorker(context: Context, parameters: WorkerParameters) :
    DeliveryWorker(context, parameters) {
    override fun doWork(): Result {
        val type = inputData.getString(EXTRA_TYPE) ?: "A"
        val alert = readyAlert(allowClosed = type == "C") ?: return Result.success()
        val target = dao.getConfig()?.platformPhone.orEmpty()
        if (alert.latitude == null || alert.longitude == null || alert.precisionMeters == null ||
            alert.currentLocationAgeSeconds() == null
        ) {
            requestLastLocation(alert)
            return Result.retry()
        }
        if (target.isBlank()) {
            dao.updateSmsState(alert.clientAlertId, "NUMERO_PLATAFORMA_REQUERIDO")
            return Result.retry()
        }
        if (type == "C" && dao.successfulAttemptCountForType(alert.clientAlertId, "PLATFORM_SMS", "A") == 0) {
            return Result.success()
        }
        return when (SmsDelivery.sendPlatform(applicationContext, dao, alert, type)) {
            SmsDispatchOutcome.QUEUED, SmsDispatchOutcome.ALREADY_ACCEPTED -> Result.success()
            SmsDispatchOutcome.ALREADY_IN_PROGRESS, SmsDispatchOutcome.RETRY -> Result.retry()
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
        return if (SmsDelivery.sendTrustedContacts(applicationContext, dao, alert)) {
            Result.success()
        } else {
            Result.retry()
        }
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
                if (attemptId >= 0L) {
                    val details = attempt?.detail.orEmpty().split(";")
                        .filter { it.isNotBlank() && !it.startsWith("resultCode=") }
                        .toMutableList()
                    if (event == "SENT" && callbackCode == Activity.RESULT_OK) {
                        details.removeAll { it.startsWith("sentAtMs=") }
                        details.add("sentAtMs=${System.currentTimeMillis()}")
                    }
                    details.add("resultCode=$callbackCode")
                    dao.updateAttempt(attemptId, status, details.joinToString(";"))
                }
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
                                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                                .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                                .build(),
                        )
                    } else {
                        manager.enqueueUniqueWork(
                            uniqueName,
                            ExistingWorkPolicy.REPLACE,
                            OneTimeWorkRequestBuilder<TrustedContactsWorker>()
                                .setInputData(input)
                                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
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
