package pe.georescue.protection

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.app.NotificationManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

class MainActivity : Activity() {
    private var pendingProtectionStart = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val state = TextView(this).apply {
            textSize = 20f
            gravity = Gravity.CENTER
            text = if (isProtectionEnabled()) "Protección sísmica configurada" else "Protección sísmica inactiva"
        }
        val start = Button(this).apply {
            text = "Activar protección"
            setOnClickListener {
                if (requestNotificationsIfNeeded()) startProtection()
            }
        }
        val stop = Button(this).apply {
            text = "Desactivar protección"
            setOnClickListener {
                startService(Intent(this@MainActivity, ProtectionService::class.java).apply {
                    action = ProtectionService.ACTION_STOP
                })
                state.text = "Protección sísmica inactiva"
            }
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(24, 24, 24, 24)
            addView(state)
            addView(start)
            addView(stop)
        })
    }

    private fun requestNotificationsIfNeeded(): Boolean {
        if (
            Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
            return false
        }
        return true
    }

    private fun startProtection() {
        if (
            Build.VERSION.SDK_INT >= 34 &&
            !getSystemService(NotificationManager::class.java).canUseFullScreenIntent()
        ) {
            pendingProtectionStart = true
            startActivity(
                Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT)
                    .setData(Uri.parse("package:$packageName")),
            )
            return
        }
        val intent = Intent(this, ProtectionService::class.java).apply { action = ProtectionService.ACTION_START }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
    }

    private fun isProtectionEnabled(): Boolean =
        getSharedPreferences(ProtectionService.PREFERENCES, MODE_PRIVATE)
            .getBoolean(ProtectionService.KEY_ENABLED, false)

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_NOTIFICATIONS && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            startProtection()
        }
    }

    override fun onResume() {
        super.onResume()
        if (!pendingProtectionStart) return
        pendingProtectionStart = false
        if (
            Build.VERSION.SDK_INT < 34 ||
            getSystemService(NotificationManager::class.java).canUseFullScreenIntent()
        ) {
            startProtection()
        }
    }

    companion object {
        private const val REQUEST_NOTIFICATIONS = 500
    }
}
