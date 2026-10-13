package pe.georescue.protection

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat

class ProtectionService : Service(), SensorEventListener {
    private lateinit var detector: EarthquakeDetector
    private lateinit var eventStore: DetectionEventStore
    private lateinit var sensorManager: SensorManager
    private var wakeLock: PowerManager.WakeLock? = null
    private var registered = false

    override fun onCreate() {
        super.onCreate()
        detector = EarthquakeDetector()
        eventStore = DetectionEventStore(this)
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            getSharedPreferences(PREFERENCES, MODE_PRIVATE).edit().putBoolean(KEY_ENABLED, false).apply()
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_AUTO_ALERT) {
            sendBroadcast(
                Intent(ACTION_AUTO_ALERT).setPackage(packageName).apply {
                    putExtra(EXTRA_EVENT_ID, intent.getLongExtra(EXTRA_EVENT_ID, -1))
                    putExtra(EXTRA_SEVERITY, intent.getIntExtra(EXTRA_SEVERITY, 3))
                    putExtra(EXTRA_ALERT_TYPE, "A")
                },
            )
            return START_STICKY
        }

        getSharedPreferences(PREFERENCES, MODE_PRIVATE).edit().putBoolean(KEY_ENABLED, true).apply()
        startForeground(NOTIFICATION_ID, protectionNotification())
        val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        if (accelerometer == null) {
            stopWithFailure("Este teléfono no informa un acelerómetro.")
            return START_NOT_STICKY
        }
        if (!registered) {
            registered = sensorManager.registerListener(
                this,
                accelerometer,
                SensorManager.SENSOR_DELAY_GAME,
            )
        }
        if (!registered) {
            stopWithFailure("Android no permitió activar el acelerómetro.")
            return START_NOT_STICKY
        }
        acquireWakeLock()
        return START_STICKY
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event == null || event.sensor.type != Sensor.TYPE_ACCELEROMETER) return
        when (val result = detector.process(event.timestamp, event.values[0].toDouble(),
            event.values[1].toDouble(), event.values[2].toDouble())) {
            is DetectorResult.Candidate -> openCountdown(result.metrics)
            is DetectorResult.Discarded -> eventStore.record(result.metrics, "DISCARDED")
            null -> Unit
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    override fun onDestroy() {
        if (registered) sensorManager.unregisterListener(this)
        wakeLock?.let { if (it.isHeld) it.release() }
        getSharedPreferences(PREFERENCES, MODE_PRIVATE).edit().putBoolean(KEY_ENABLED, false).apply()
        eventStore.close()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun openCountdown(metrics: DetectionMetrics) {
        val eventId = eventStore.record(metrics, "PENDING")
        val countdownIntent = Intent(this, CountdownActivity::class.java).apply {
            putExtra(CountdownActivity.EXTRA_EVENT_ID, eventId)
            putExtra(CountdownActivity.EXTRA_SEVERITY, metrics.severityHint)
            putExtra(CountdownActivity.EXTRA_COUNTDOWN, metrics.countdownSeconds)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        val fullScreenIntent = PendingIntent.getActivity(
            this,
            eventId.toInt(),
            countdownIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, ALERT_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("Posible movimiento sísmico")
            .setContentText("Responde antes de que termine la cuenta regresiva.")
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setFullScreenIntent(fullScreenIntent, true)
            .setOngoing(true)
            .setAutoCancel(false)
            .build()
        getSystemService(NotificationManager::class.java).notify(ALERT_NOTIFICATION_ID, notification)
    }

    private fun protectionNotification(): Notification =
        NotificationCompat.Builder(this, PROTECTION_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setContentTitle("Protección sísmica activa")
            .setContentText("Vigilancia local del acelerómetro activa.")
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setOngoing(true)
            .build()

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(
                NotificationChannel(
                    PROTECTION_CHANNEL_ID,
                    "Protección sísmica",
                    NotificationManager.IMPORTANCE_LOW,
                ),
            )
            manager.createNotificationChannel(
                NotificationChannel(
                    ALERT_CHANNEL_ID,
                    "Alertas de detección",
                    NotificationManager.IMPORTANCE_HIGH,
                ).apply {
                    lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                    enableVibration(true)
                    setBypassDnd(true)
                    setSound(
                        android.media.RingtoneManager.getDefaultUri(android.media.RingtoneManager.TYPE_ALARM),
                        android.media.AudioAttributes.Builder()
                            .setUsage(android.media.AudioAttributes.USAGE_ALARM)
                            .build(),
                    )
                },
            )
        }
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Georescue:Protection")
            .apply { acquire() }
    }

    private fun stopWithFailure(message: String) {
        getSharedPreferences(PREFERENCES, MODE_PRIVATE).edit().putBoolean(KEY_ENABLED, false).apply()
        val failure = NotificationCompat.Builder(this, PROTECTION_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle("Protección sísmica inactiva")
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, failure)
        stopSelf()
    }

    companion object {
        const val ACTION_START = "pe.georescue.protection.START"
        const val ACTION_STOP = "pe.georescue.protection.STOP"
        const val ACTION_AUTO_ALERT = "pe.georescue.protection.AUTO_ALERT"
        const val EXTRA_EVENT_ID = "event_id"
        const val EXTRA_SEVERITY = "severity"
        const val EXTRA_ALERT_TYPE = "alert_type"
        const val PREFERENCES = "protection"
        const val KEY_ENABLED = "enabled"

        private const val NOTIFICATION_ID = 101
        private const val ALERT_NOTIFICATION_ID = 102
        private const val PROTECTION_CHANNEL_ID = "protection"
        private const val ALERT_CHANNEL_ID = "detection_alert"
    }
}
