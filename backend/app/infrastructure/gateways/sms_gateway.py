import base64
import hashlib
import hmac
import json
import logging
from typing import Dict, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, parse_qsl
from urllib.request import Request, urlopen

from app.core.config import settings
from app.domain.interfaces.gateways import ISMSGateway

logger = logging.getLogger("georescue.sms")


class ConsoleSMSGateway(ISMSGateway):
    """Fallback sin entrega real; el webhook exige firma HMAC configurada."""

    def enviar(self, destinatario: str, mensaje: str) -> Dict[str, Any]:
        if settings.SMS_CONSOLE_PRINT_MESSAGES:
            # Modo de desarrollo explícito: no se envía nada a la red telefónica;
            # el texto solo se muestra en la terminal donde corre el backend.
            print(f"[SMS de desarrollo, NO enviado] para {destinatario}: {mensaje}", flush=True)
            return {"estado": "MOSTRADO_EN_CONSOLA", "provider_id": None}
        logger.warning("Gateway SMS de consola: envío no realizado (destino enmascarado).")
        return {"estado": "NO_CONFIGURADO", "provider_id": None}

    def validar_firma_webhook(
        self,
        url: str,
        headers: Dict[str, str],
        body: bytes,
        content_type: str,
    ) -> bool:
        if not settings.SMS_WEBHOOK_SECRET:
            return False
        signature = _header_value(headers, settings.SMS_SIGNATURE_HEADER)
        if not signature:
            return False
        expected = hmac.new(
            settings.SMS_WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        supplied = signature.removeprefix("sha256=").strip().lower()
        return hmac.compare_digest(expected, supplied)


class TwilioSMSGateway(ISMSGateway):
    """Integración con Twilio usando su API REST y firma estándar de webhook."""

    def enviar(self, destinatario: str, mensaje: str) -> Dict[str, Any]:
        required = (
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            settings.TWILIO_FROM_NUMBER,
        )
        if not all(required):
            raise RuntimeError("Falta configurar las credenciales Twilio.")

        url = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        )
        body = urlencode({
            "To": destinatario,
            "From": settings.TWILIO_FROM_NUMBER,
            "Body": mensaje,
        }).encode("ascii")
        credentials = base64.b64encode(
            f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode("utf-8")
        ).decode("ascii")
        request = Request(
            url,
            data=body,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Twilio rechazó el SMS (HTTP {exc.code}).") from exc
        except URLError as exc:
            raise RuntimeError("No se pudo contactar al proveedor Twilio.") from exc
        return {"estado": result.get("status"), "provider_id": result.get("sid")}

    def validar_firma_webhook(
        self,
        url: str,
        headers: Dict[str, str],
        body: bytes,
        content_type: str,
    ) -> bool:
        if not settings.TWILIO_AUTH_TOKEN:
            return False
        signature = _header_value(headers, "X-Twilio-Signature")
        if not signature:
            return False

        signed_value = url
        if "application/x-www-form-urlencoded" in content_type.lower():
            try:
                params = parse_qsl(body.decode("utf-8"), keep_blank_values=True)
            except UnicodeDecodeError:
                return False
            grouped: Dict[str, list[str]] = {}
            for key, value in params:
                grouped.setdefault(key, []).append(value)
            for key in sorted(grouped):
                signed_value += key + "".join(sorted(grouped[key]))

        digest = hmac.new(
            settings.TWILIO_AUTH_TOKEN.encode("utf-8"),
            signed_value.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        expected = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(expected, signature.strip())


def _header_value(headers: Dict[str, str], name: str) -> str:
    target = name.lower()
    return next((value for key, value in headers.items() if key.lower() == target), "")


def create_sms_gateway() -> ISMSGateway:
    provider = settings.SMS_PROVIDER
    if provider == "console":
        return ConsoleSMSGateway()
    if provider == "twilio":
        return TwilioSMSGateway()
    raise RuntimeError(f"Proveedor SMS no soportado: {provider}")
