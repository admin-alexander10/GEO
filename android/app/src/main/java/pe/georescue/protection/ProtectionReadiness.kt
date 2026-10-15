package pe.georescue.protection

data class ProtectionRequirements(
    val fineLocation: Boolean,
    val backgroundLocation: Boolean,
    val sms: Boolean,
    val batteryUnrestricted: Boolean,
    val platformPhone: Boolean,
    val signingSecret: Boolean,
    val verifiedPhone: Boolean,
    val consentedContact: Boolean,
    val apiToken: Boolean,
    val apiUrlConfigured: Boolean,
    val notifications: Boolean,
    val fullScreenIntent: Boolean,
)

object ProtectionReadiness {
    fun missingSteps(requirements: ProtectionRequirements): List<String> = buildList {
        if (!requirements.fineLocation) add("Permitir ubicación precisa.")
        if (!requirements.backgroundLocation) add("Permitir ubicación en segundo plano.")
        if (!requirements.sms) add("Permitir el envío de SMS.")
        if (!requirements.batteryUnrestricted) add("Quitar la restricción de batería.")
        if (!requirements.platformPhone) add("Configurar el número SMS de la plataforma.")
        if (!requirements.signingSecret) add("Registrar el dispositivo y guardar su secreto.")
        if (!requirements.verifiedPhone) add("Verificar el teléfono con OTP.")
        if (!requirements.consentedContact) add("Agregar un contacto con consentimiento.")
        if (!requirements.apiToken) add("Iniciar sesión en la API.")
        if (!requirements.apiUrlConfigured) add("Configurar una URL HTTPS para la API.")
        if (!requirements.notifications) add("Permitir notificaciones.")
        if (!requirements.fullScreenIntent) add("Permitir alertas a pantalla completa.")
    }

    fun isReady(requirements: ProtectionRequirements): Boolean = missingSteps(requirements).isEmpty()

    fun deliveryLabel(result: String, target: String): String? =
        when (result) {
            "SMS_SENT_TO_NETWORK" -> "SMS enviado a la red (sin confirmación) a $target."
            "SMS_DELIVERED" -> "SMS entregado a $target."
            "SEND_FAILED" -> "SMS no enviado a $target."
            "DELIVERY_NOT_CONFIRMED" -> "Entrega no confirmada a $target."
            else -> null
        }
}
