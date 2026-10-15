package pe.georescue.protection

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.os.Handler
import android.os.Looper
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.tasks.CancellationTokenSource
import java.util.concurrent.Executors
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean

object AlertDelivery {
    const val ACTION_STATUS_CHANGED = "pe.georescue.protection.STATUS_CHANGED"
    private val io = Executors.newSingleThreadExecutor()
    private val locationSubscriptions = ConcurrentHashMap<String, LocationWatch>()

    fun startAutomaticAlert(context: Context, eventId: Long, severity: Int) {
        val appContext = context.applicationContext
        val fused: FusedLocationProviderClient? = try {
            LocationServices.getFusedLocationProviderClient(appContext)
        } catch (_: IllegalStateException) {
            null
        }
        val dispatched = AtomicBoolean(false)
        val handler = Handler(Looper.getMainLooper())
        val tokenSource = CancellationTokenSource()
        val requestTime = System.currentTimeMillis()
        val deviceId = android.provider.Settings.Secure.getString(
            appContext.contentResolver,
            android.provider.Settings.Secure.ANDROID_ID,
        ) ?: appContext.packageName
        val clientAlertId = Gr1Message.clientAlertIdForEvent(eventId, deviceId)
        val locationUpdatesRequested = AtomicBoolean(false)
        val followupCallback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                result.locations.forEach { updateImprovedLocation(appContext, clientAlertId, it) }
            }
        }

        fun requestFollowupLocation() {
            val locationClient = fused ?: return
            if (!locationUpdatesRequested.compareAndSet(false, true)) return
            try {
                locationClient.requestLocationUpdates(
                    LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 3_000L)
                        .setDurationMillis(30_000L)
                        .build(),
                    followupCallback,
                    Looper.getMainLooper(),
                )
                handler.postDelayed(
                    {
                        locationClient.removeLocationUpdates(followupCallback)
                        locationSubscriptions.remove(clientAlertId)
                    },
                    30_000L,
                )
                locationSubscriptions[clientAlertId] =
                    LocationWatch(locationClient, followupCallback, tokenSource)
            } catch (_: SecurityException) {
                locationUpdatesRequested.set(false)
            }
        }

        fun enqueue(location: Location?) {
            if (!dispatched.compareAndSet(false, true)) {
                if (location != null) updateImprovedLocation(appContext, clientAlertId, location)
                return
            }
            handler.removeCallbacksAndMessages(null)
            if (location != null) tokenSource.cancel()
            requestFollowupLocation()
            val now = System.currentTimeMillis()
            val age = location?.let { ((now - it.time).coerceAtLeast(0L) / 1000L).coerceAtMost(31536000L) }
            val alert = AutomaticAlertEntity(
                clientAlertId = clientAlertId,
                detectionEventId = eventId,
                severity = severity.coerceIn(1, 5),
                latitude = location?.latitude,
                longitude = location?.longitude,
                precisionMeters = location?.let(::precisionMeters),
                ageSeconds = age,
                locationAgeRecordedAt = location?.let { now },
                timestampSeconds = requestTime / 1000L,
            )
            io.execute {
                val dao = ProtectionDatabase.get(appContext).protectionDao()
                dao.insertAlert(alert)
                val eventStore = DetectionEventStore(appContext)
                try {
                    eventStore.updateResult(eventId, "AUTO_ALERT_TRIGGERED")
                } finally {
                    eventStore.close()
                }
                val savedAlert = dao.getAlert(clientAlertId) ?: alert
                try {
                    enqueueApiWorker(appContext, clientAlertId)
                } catch (error: Exception) {
                    Log.e(TAG, "No se pudo programar el envío API de la alerta.", error)
                }
                try {
                    try {
                        SmsDelivery.sendPlatform(appContext, dao, savedAlert, "A")
                    } catch (error: Exception) {
                        Log.e(TAG, "No se pudo iniciar el envío inmediato del SMS firmado.", error)
                    }
                    try {
                        SmsDelivery.sendTrustedContacts(appContext, dao, savedAlert)
                    } catch (error: Exception) {
                        Log.e(TAG, "No se pudo iniciar el envío inmediato a contactos.", error)
                    }
                } finally {
                    try {
                        enqueueSmsWorkers(appContext, clientAlertId)
                    } catch (error: Exception) {
                        Log.e(TAG, "No se pudieron programar los reintentos SMS.", error)
                    }
                    notifyStatusChanged(appContext)
                }
            }
        }

        val hasLocationPermission =
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.ACCESS_FINE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED &&
                (Build.VERSION.SDK_INT < 29 ||
                    ContextCompat.checkSelfPermission(
                        appContext,
                        Manifest.permission.ACCESS_BACKGROUND_LOCATION,
                    ) == PackageManager.PERMISSION_GRANTED)
        if (!hasLocationPermission) {
            enqueue(null)
            return
        }
        if (fused == null) {
            enqueue(null)
            return
        }
        val timeout = Runnable {
            try {
                fused.lastLocation
                    .addOnSuccessListener { enqueue(it) }
                    .addOnFailureListener { enqueue(null) }
                handler.postDelayed({ enqueue(null) }, 750L)
            } catch (_: SecurityException) {
                enqueue(null)
            }
        }
        handler.postDelayed(timeout, 5_000L)
        try {
            fused.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, tokenSource.token)
                .addOnSuccessListener { if (it != null) enqueue(it) }
                .addOnFailureListener { }
        } catch (_: SecurityException) {
            enqueue(null)
        }
    }

    fun enqueueDispatchWorkers(context: Context, clientAlertId: String) {
        enqueueApiWorker(context, clientAlertId)
        enqueueSmsWorkers(context, clientAlertId)
    }

    private fun enqueueApiWorker(context: Context, clientAlertId: String) {
        val manager = WorkManager.getInstance(context)
        val input = Data.Builder().putString(DeliveryWorker.EXTRA_ALERT_ID, clientAlertId).build()
        val network = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        manager.enqueueUniqueWork(
            "alert-api:$clientAlertId",
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<ApiAlertWorker>().setInputData(input).setConstraints(network).build(),
        )
    }

    private fun enqueueSmsWorkers(context: Context, clientAlertId: String) {
        val manager = WorkManager.getInstance(context)
        val input = Data.Builder().putString(DeliveryWorker.EXTRA_ALERT_ID, clientAlertId).build()
        manager.enqueueUniqueWork(
            "alert-signed-sms:$clientAlertId",
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<PlatformSmsWorker>()
                .setInputData(input)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build(),
        )
        manager.enqueueUniqueWork(
            "alert-contacts-sms:$clientAlertId",
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<TrustedContactsWorker>()
                .setInputData(input)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build(),
        )
    }

    fun enqueueLocationUpdate(context: Context, clientAlertId: String) {
        val input = Data.Builder().putString(DeliveryWorker.EXTRA_ALERT_ID, clientAlertId).build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "alert-location-update:$clientAlertId",
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<LocationUpdateWorker>().setInputData(input).build(),
        )
    }

    fun cancelLatestAlert(context: Context) {
        io.execute {
            val dao = ProtectionDatabase.get(context).protectionDao()
            val alert = dao.getLatestOpenAlert() ?: return@execute
            if (dao.closeAlert(alert.clientAlertId, "CANCELLED_BY_USER") != 1) return@execute
            locationSubscriptions.remove(alert.clientAlertId)?.let { watch ->
                watch.cancellationToken.cancel()
                watch.client.removeLocationUpdates(watch.callback)
            }
            val eventStore = DetectionEventStore(context)
            try {
                eventStore.updateResult(alert.detectionEventId, "USER_OK")
            } finally {
                eventStore.close()
            }
            if (dao.successfulAttemptCountForType(alert.clientAlertId, "PLATFORM_SMS", "A") > 0) {
                enqueueCancellationSms(context, alert.clientAlertId)
            }
            alert.serverAlertId?.let { enqueueServerCancellation(context, alert.clientAlertId, it) }
            notifyStatusChanged(context)
        }
    }

    fun notifyStatusChanged(context: Context) {
        context.sendBroadcast(Intent(ACTION_STATUS_CHANGED).setPackage(context.packageName))
    }

    fun enqueueCancellationSms(context: Context, clientAlertId: String) {
        val input = Data.Builder()
            .putString(DeliveryWorker.EXTRA_ALERT_ID, clientAlertId)
            .putString(DeliveryWorker.EXTRA_TYPE, "C")
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "alert-signed-sms-cancel:$clientAlertId",
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<PlatformSmsWorker>()
                .setInputData(input)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build(),
        )
    }

    fun enqueueServerCancellation(context: Context, clientAlertId: String, serverAlertId: Int) {
        val input = Data.Builder()
            .putString(DeliveryWorker.EXTRA_ALERT_ID, clientAlertId)
            .putInt(ApiAlertCancellationWorker.EXTRA_SERVER_ALERT_ID, serverAlertId)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "alert-api-cancel:$clientAlertId",
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<ApiAlertCancellationWorker>()
                .setInputData(input)
                .setConstraints(
                    Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build(),
                )
                .build(),
        )
    }

    fun recoverOpenAlerts(context: Context) {
        val dao = ProtectionDatabase.get(context).protectionDao()
        dao.getOpenAlerts().forEach { alert ->
            enqueueDispatchWorkers(context, alert.clientAlertId)
        }
    }

    private fun updateImprovedLocation(context: Context, clientAlertId: String, location: Location) {
        io.execute {
            val dao = ProtectionDatabase.get(context).protectionDao()
            val alert = dao.getAlert(clientAlertId) ?: return@execute
            val now = System.currentTimeMillis()
            val age = ((now - location.time).coerceAtLeast(0L) / 1000L).coerceAtMost(31536000L)
            val precision = precisionMeters(location)
            if (
                alert.status == "OPEN" &&
                (
                    alert.latitude == null ||
                        alert.longitude == null ||
                        alert.precisionMeters == null ||
                        precision < alert.precisionMeters ||
                        (alert.ageSeconds != null && age < alert.ageSeconds)
                    ) &&
                dao.updateLocation(
                    alert.clientAlertId,
                    location.latitude,
                    location.longitude,
                    precision,
                    age,
                    now,
                ) == 1
            ) {
                enqueueLocationUpdate(context, alert.clientAlertId)
            }
        }
    }

    private fun precisionMeters(location: Location): Int =
        if (location.hasAccuracy()) location.accuracy.toInt().coerceIn(0, 100000) else 100000

    private data class LocationWatch(
        val client: FusedLocationProviderClient,
        val callback: LocationCallback,
        val cancellationToken: CancellationTokenSource,
    )

    private const val TAG = "AlertDelivery"
}

class RetryOpenAlertsWorker(context: Context, parameters: androidx.work.WorkerParameters) :
    androidx.work.Worker(context, parameters) {
    override fun doWork(): Result {
        AlertDelivery.recoverOpenAlerts(applicationContext)
        return Result.success()
    }
}
