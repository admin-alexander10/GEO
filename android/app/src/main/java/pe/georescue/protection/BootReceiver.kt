package pe.georescue.protection

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        val enabled = context.getSharedPreferences(ProtectionService.PREFERENCES, Context.MODE_PRIVATE)
            .getBoolean(ProtectionService.KEY_ENABLED, false)
        if (!enabled) return
        val serviceIntent = Intent(context, ProtectionService::class.java).apply {
            action = ProtectionService.ACTION_START
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }
}
