package pe.georescue.protection

import android.app.Activity
import android.app.NotificationManager
import android.os.Bundle
import android.os.CountDownTimer
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

class CountdownActivity : Activity() {
    private lateinit var eventStore: DetectionEventStore
    private lateinit var countdownLabel: TextView
    private var timer: CountDownTimer? = null
    private var eventId: Long = -1
    private var severity = 3
    private var countdownSeconds = 10
    private var completed = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON,
        )
        eventStore = DetectionEventStore(this)
        eventId = intent.getLongExtra(EXTRA_EVENT_ID, -1)
        severity = intent.getIntExtra(EXTRA_SEVERITY, 3)
        countdownSeconds = intent.getIntExtra(EXTRA_COUNTDOWN, if (severity >= 4) 7 else 10)
        check(eventId >= 0) { "Missing detection event ID." }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(32, 48, 32, 48)
        }
        val title = TextView(this).apply {
            text = "¿ESTÁS BIEN?"
            textSize = 34f
            gravity = Gravity.CENTER
        }
        countdownLabel = TextView(this).apply {
            textSize = 64f
            gravity = Gravity.CENTER
        }
        val safeButton = Button(this).apply {
            text = "ESTOY BIEN"
            textSize = 26f
            setOnClickListener { confirmSafe() }
        }
        layout.addView(title)
        layout.addView(countdownLabel)
        layout.addView(
            safeButton,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                180,
            ),
        )
        setContentView(layout)
        startCountdown()
    }

    override fun onDestroy() {
        timer?.cancel()
        if (::eventStore.isInitialized) eventStore.close()
        super.onDestroy()
    }

    private fun startCountdown() {
        timer = object : CountDownTimer(countdownSeconds * 1000L, 250L) {
            override fun onTick(millisUntilFinished: Long) {
                countdownLabel.text = ((millisUntilFinished + 999L) / 1000L).toString()
            }

            override fun onFinish() {
                if (completed) return
                completed = true
                eventStore.updateResult(eventId, "AUTO_ALERT_TRIGGERED")
                val trigger = android.content.Intent(this@CountdownActivity, ProtectionService::class.java).apply {
                    action = ProtectionService.ACTION_AUTO_ALERT
                    putExtra(ProtectionService.EXTRA_EVENT_ID, eventId)
                    putExtra(ProtectionService.EXTRA_SEVERITY, severity)
                    putExtra(ProtectionService.EXTRA_ALERT_TYPE, "A")
                }
                startService(trigger)
                getSystemService(NotificationManager::class.java).cancel(102)
                finish()
            }
        }.start()
    }

    private fun confirmSafe() {
        if (completed) return
        completed = true
        timer?.cancel()
        eventStore.updateResult(eventId, "USER_OK")
        getSystemService(NotificationManager::class.java).cancel(102)
        finish()
    }

    companion object {
        const val EXTRA_EVENT_ID = "event_id"
        const val EXTRA_SEVERITY = "severity"
        const val EXTRA_COUNTDOWN = "countdown_seconds"
    }
}
