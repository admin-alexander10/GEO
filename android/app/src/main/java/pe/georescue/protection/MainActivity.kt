package pe.georescue.protection

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val io = Executors.newSingleThreadExecutor()
    private var pendingProtectionStart = false
    private lateinit var status: TextView
    private lateinit var apiUrl: EditText
    private lateinit var platformPhone: EditText
    private lateinit var username: EditText
    private lateinit var password: EditText
    private lateinit var phone: EditText
    private lateinit var otp: EditText
    private lateinit var contactName: EditText
    private lateinit var contactPhone: EditText
    private lateinit var contactConsent: CheckBox
    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == AlertDelivery.ACTION_STATUS_CHANGED) refreshStatus()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply { textSize = 18f }
        apiUrl = field("URL HTTPS de la API (p. ej. https://api.ejemplo.pe)")
        platformPhone = field("Número SMS de la plataforma (+E.164)")
        username = field("Usuario GEORESCUE")
        password = field("Contraseña", password = true)
        phone = field("Teléfono propio verificado (+E.164)")
        otp = field("Código OTP de 6 dígitos")
        contactName = field("Nombre del contacto de confianza")
        contactPhone = field("Teléfono del contacto (+E.164)")
        contactConsent = CheckBox(this).apply {
            text = "Confirmo que este contacto aceptó recibir SMS de emergencia."
        }
        val explanation = TextView(this).apply {
            text = "Ubicación precisa y en segundo plano: se usa solo al dispararse una alerta. " +
                "Servicio de ubicación en primer plano: permite el GPS con la pantalla bloqueada. " +
                "SMS: envía la alerta firmada por la red celular. Internet y estado de red: " +
                "envían/reintentan la alerta en la API. En segundo plano se requiere permiso " +
                "aunque la pantalla esté bloqueada."
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(24, 24, 24, 24)
            addView(status)
            addView(explanation)
            addView(apiUrl)
            addView(platformPhone)
            addView(button("Guardar URL y número de plataforma") { saveLocalConfiguration() })
            addView(username)
            addView(password)
            addView(button("Iniciar sesión en la API") { login() })
            addView(phone)
            addView(button("Solicitar OTP") { requestOtp() })
            addView(otp)
            addView(button("Verificar OTP") { verifyOtp() })
            addView(button("Registrar este dispositivo y guardar el secreto") { registerDevice() })
            addView(contactName)
            addView(contactPhone)
            addView(contactConsent)
            addView(button("Agregar contacto con consentimiento") { addTrustedContact() })
            addView(button("Solicitar permisos de ubicación precisa, segundo plano y SMS") {
                requestProtectionPermissions()
            })
            addView(button("Abrir ajustes para quitar restricción de batería") {
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            })
            addView(button("Activar protección") { startProtectionWhenReady() })
            addView(button("Desactivar protección") {
                startService(Intent(this@MainActivity, ProtectionService::class.java).apply {
                    action = ProtectionService.ACTION_STOP
                })
                refreshStatus()
            })
            addView(button("Estoy bien / cancelar última alerta") {
                AlertDelivery.cancelLatestAlert(this@MainActivity)
                Toast.makeText(this@MainActivity, "Se solicitará cancelación si hay una alerta activa.", Toast.LENGTH_LONG).show()
                refreshStatus()
            })
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(
                ScrollView(this@MainActivity).apply { addView(content) },
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0,
                    1f,
                ),
            )
            addView(emergencyButtons())
        })
        refreshStatus()
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
        if (!pendingProtectionStart) return
        pendingProtectionStart = false
        if (
            Build.VERSION.SDK_INT < 34 ||
            getSystemService(NotificationManager::class.java).canUseFullScreenIntent()
        ) {
            startProtectionWhenReady()
        }
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(AlertDelivery.ACTION_STATUS_CHANGED)
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(statusReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(statusReceiver, filter)
        }
    }

    override fun onStop() {
        unregisterReceiver(statusReceiver)
        super.onStop()
    }

    private fun field(hint: String, password: Boolean = false): EditText =
        EditText(this).apply {
            this.hint = hint
            singleLine = true
            if (password) inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }

    private fun button(label: String, action: () -> Unit): Button =
        Button(this).apply {
            text = label
            setOnClickListener { action() }
        }

    private fun emergencyButtons(): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            listOf("105", "116", "106").forEach { number ->
                addView(button(number) {
                    startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number")))
                }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            }
        }

    private fun saveLocalConfiguration() {
        val base = apiUrl.text.toString().trim().trimEnd('/')
        val platform = platformPhone.text.toString().trim()
        if (!validE164(platform)) {
            showMessage("El número de plataforma debe estar en formato E.164.")
            return
        }
        if (!isAllowedApiUrl(base)) {
            showMessage("Configura una URL HTTPS válida para la API.")
            return
        }
        runDatabaseAction("Configuración local guardada.") { dao ->
            val old = dao.getConfig() ?: ProtectionConfigEntity()
            dao.saveConfig(old.copy(apiBaseUrl = base, platformPhone = platform))
        }
    }

    private fun login() {
        val base = apiUrl.text.toString().trim().trimEnd('/')
        val user = username.text.toString().trim()
        val pass = password.text.toString()
        if (base.isBlank() || user.isBlank() || pass.isBlank()) {
            showMessage("Completa URL, usuario y contraseña.")
            return
        }
        if (!isAllowedApiUrl(base)) {
            showMessage("La URL de la API debe usar HTTPS.")
            return
        }
        runAction("Sesión iniciada.") {
            val old = ProtectionDatabase.get(this).protectionDao().getConfig() ?: ProtectionConfigEntity()
            val token = RescueApiClient(base).login(user, pass)
            ProtectionDatabase.get(this).protectionDao().saveConfig(
                old.copy(
                    apiBaseUrl = base,
                    username = user,
                    encryptedToken = CredentialVault.encrypt(token.toByteArray(Charsets.UTF_8)),
                ),
            )
            runOnUiThread { password.setText("") }
        }
    }

    private fun requestOtp() {
        val requestedPhone = phone.text.toString().trim()
        if (!validE164(requestedPhone)) {
            showMessage("Escribe tu teléfono en formato E.164.")
            return
        }
        runAction("Solicitud de OTP aceptada por la API.") {
            val dao = ProtectionDatabase.get(this).protectionDao()
            val config = dao.getConfig() ?: error("Inicia sesión primero.")
            val token = CredentialVault.decrypt(config.encryptedToken).toString(Charsets.UTF_8)
            RescueApiClient(config.apiBaseUrl).requestPhoneOtp(token, requestedPhone)
            dao.saveConfig(config.copy(phonePendingOtp = requestedPhone))
        }
    }

    private fun verifyOtp() {
        val code = otp.text.toString().trim()
        runAction("Teléfono verificado por la API.") {
            val dao = ProtectionDatabase.get(this).protectionDao()
            val config = dao.getConfig() ?: error("Inicia sesión primero.")
            require(code.matches(Regex("[0-9]{6}"))) { "El OTP debe tener seis dígitos." }
            val token = CredentialVault.decrypt(config.encryptedToken).toString(Charsets.UTF_8)
            RescueApiClient(config.apiBaseUrl).verifyPhoneOtp(token, config.phonePendingOtp, code)
            dao.saveConfig(config.copy(verifiedPhone = config.phonePendingOtp, phonePendingOtp = ""))
        }
    }

    private fun registerDevice() {
        runAction("Dispositivo registrado; secreto cifrado en este teléfono.") {
            val dao = ProtectionDatabase.get(this).protectionDao()
            val config = dao.getConfig() ?: error("Inicia sesión y verifica el teléfono primero.")
            require(config.verifiedPhone.isNotBlank()) { "Verifica primero el teléfono con OTP." }
            require(config.encryptedSigningSecret.isBlank()) {
                "Este dispositivo ya tiene un secreto guardado. No lo registres otra vez."
            }
            val token = CredentialVault.decrypt(config.encryptedToken).toString(Charsets.UTF_8)
            val deviceId = android.provider.Settings.Secure.getString(contentResolver, android.provider.Settings.Secure.ANDROID_ID)
                ?: error("Android no proporcionó el identificador de este dispositivo.")
            val secret = RescueApiClient(config.apiBaseUrl).registerDevice(token, deviceId)
            dao.saveConfig(
                config.copy(
                    deviceId = deviceId,
                    encryptedSigningSecret = CredentialVault.encrypt(secret.toByteArray(Charsets.UTF_8)),
                ),
            )
        }
    }

    private fun addTrustedContact() {
        val name = contactName.text.toString().trim()
        val number = contactPhone.text.toString().trim()
        if (name.isBlank() || name.length > 60 || !validE164(number) || !contactConsent.isChecked) {
            showMessage("Escribe nombre y teléfono válidos y confirma el consentimiento explícito.")
            return
        }
        runDatabaseAction("Contacto guardado solo en este dispositivo.") { dao ->
            dao.addContact(TrustedContactEntity(name = name, phone = number, consentedAt = System.currentTimeMillis()))
        }
    }

    private fun runDatabaseAction(success: String, operation: (ProtectionDao) -> Unit) {
        runAction(success) { operation(ProtectionDatabase.get(this).protectionDao()) }
    }

    private fun runAction(success: String, operation: () -> Unit) {
        io.execute {
            val result = runCatching(operation)
            runOnUiThread {
                showMessage(result.fold({ success }, { it.message ?: "No se pudo completar la operación." }))
                refreshStatus()
            }
        }
    }

    private fun requestProtectionPermissions() {
        val next = when {
            Build.VERSION.SDK_INT >= 23 && !permissionGranted(Manifest.permission.ACCESS_FINE_LOCATION) ->
                Manifest.permission.ACCESS_FINE_LOCATION
            Build.VERSION.SDK_INT >= 29 && !permissionGranted(Manifest.permission.ACCESS_BACKGROUND_LOCATION) ->
                Manifest.permission.ACCESS_BACKGROUND_LOCATION
            Build.VERSION.SDK_INT >= 23 && !permissionGranted(Manifest.permission.SEND_SMS) ->
                Manifest.permission.SEND_SMS
            Build.VERSION.SDK_INT >= 33 && !permissionGranted(Manifest.permission.POST_NOTIFICATIONS) ->
                Manifest.permission.POST_NOTIFICATIONS
            else -> null
        }
        if (next == null) {
            showMessage("Permisos de ubicación y SMS concedidos.")
        } else {
            requestPermissions(arrayOf(next), REQUEST_PROTECTION_PERMISSION)
        }
    }

    private fun startProtectionWhenReady() {
        requestProtectionPermissions()
        io.execute {
            val dao = ProtectionDatabase.get(this).protectionDao()
            val config = dao.getConfig()
            val requirements = currentRequirements(config, dao.consentedContactCount() > 0)
            runOnUiThread {
                val missing = ProtectionReadiness.missingSteps(requirements)
                if (missing == listOf("Permitir alertas a pantalla completa.")) {
                    startProtection()
                } else if (missing.isNotEmpty()) {
                    showMessage("No se puede activar:\n${missing.joinToString("\n")}")
                    refreshStatus()
                } else if (requestNotificationsIfNeeded()) {
                    startProtection()
                }
            }
        }
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
        refreshStatus()
    }

    private fun currentRequirements(config: ProtectionConfigEntity?, hasContact: Boolean): ProtectionRequirements =
        ProtectionRequirements(
            fineLocation = permissionGranted(Manifest.permission.ACCESS_FINE_LOCATION),
            backgroundLocation = Build.VERSION.SDK_INT < 29 ||
                permissionGranted(Manifest.permission.ACCESS_BACKGROUND_LOCATION),
            sms = permissionGranted(Manifest.permission.SEND_SMS),
            batteryUnrestricted = Build.VERSION.SDK_INT < 23 ||
                getSystemService(android.os.PowerManager::class.java).isIgnoringBatteryOptimizations(packageName),
            platformPhone = !config?.platformPhone.isNullOrBlank(),
            signingSecret = !config?.encryptedSigningSecret.isNullOrBlank(),
            verifiedPhone = !config?.verifiedPhone.isNullOrBlank(),
            consentedContact = hasContact,
            apiToken = !config?.encryptedToken.isNullOrBlank(),
            apiUrlConfigured = config?.apiBaseUrl?.let(::isAllowedApiUrl) == true,
            notifications = Build.VERSION.SDK_INT < 33 ||
                permissionGranted(Manifest.permission.POST_NOTIFICATIONS),
            fullScreenIntent = Build.VERSION.SDK_INT < 34 ||
                getSystemService(NotificationManager::class.java).canUseFullScreenIntent(),
        )

    private fun refreshStatus() {
        io.execute {
            val dao = ProtectionDatabase.get(this).protectionDao()
            val config = dao.getConfig()
            val requirements = currentRequirements(config, dao.consentedContactCount() > 0)
            val missing = ProtectionReadiness.missingSteps(requirements)
            val latest = dao.getLatestAlert()
            val attempts = latest?.let { dao.getAttempts(it.clientAlertId) }.orEmpty()
            runOnUiThread {
                val active = isProtectionEnabled() && ProtectionReadiness.isReady(requirements)
                val lines = mutableListOf(if (active) "🟢 Protección activa" else "🔴 Protección incompleta o inactiva")
                if (Build.VERSION.SDK_INT >= 29 && !requirements.backgroundLocation) {
                    lines.add("Sin ubicación en segundo plano: no se obtendrá GPS con la pantalla bloqueada.")
                }
                lines.addAll(missing)
                if (latest != null) {
                    lines.add("Alerta ${latest.clientAlertId}: API ${latest.apiState}; SMS ${latest.signedSmsState}.")
                    if (latest.status == "CANCELLED_BY_USER") lines.add("Cancelación solicitada localmente.")
                    if (latest.apiState == "RECIBIDA_POR_SERVIDOR") lines.add("Recibida por el servidor.")
                    if (latest.apiState == "CANCELADA_EN_SERVIDOR") lines.add("Cancelación recibida por el servidor.")
                    if (latest.apiState.startsWith("CANCELACION_")) lines.add("Cancelación API pendiente de confirmación.")
                    attempts.forEach { attempt ->
                        ProtectionReadiness.deliveryLabel(attempt.result, attempt.target)?.let(lines::add)
                    }
                }
                status.text = lines.distinct().joinToString("\n")
                if (config != null) {
                    if (!apiUrl.hasFocus()) apiUrl.setText(config.apiBaseUrl)
                    if (!platformPhone.hasFocus()) platformPhone.setText(config.platformPhone)
                    if (!username.hasFocus()) username.setText(config.username)
                    if (!phone.hasFocus()) phone.setText(config.phonePendingOtp.ifBlank { config.verifiedPhone })
                }
            }
        }
    }

    private fun isProtectionEnabled(): Boolean =
        getSharedPreferences(ProtectionService.PREFERENCES, MODE_PRIVATE)
            .getBoolean(ProtectionService.KEY_ENABLED, false)

    private fun permissionGranted(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun validE164(value: String): Boolean = value.matches(Regex("^\\+[1-9][0-9]{7,14}$"))

    private fun isAllowedApiUrl(value: String): Boolean =
        value.startsWith("https://")

    private fun showMessage(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_PROTECTION_PERMISSION) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
                requestProtectionPermissions()
            } else if (permissions.firstOrNull() == Manifest.permission.ACCESS_BACKGROUND_LOCATION) {
                showMessage("Sin ubicación en segundo plano no se leerá GPS al dispararse la alerta.")
            }
            refreshStatus()
        }
        if (requestCode == REQUEST_NOTIFICATIONS && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            startProtectionWhenReady()
        }
    }

    companion object {
        private const val REQUEST_NOTIFICATIONS = 500
        private const val REQUEST_PROTECTION_PERMISSION = 501
    }
}
