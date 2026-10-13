import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import EstadoConfirmacion, OrigenAlerta, TipoEmergencia
from app.infrastructure.gateways.sms_gateway import create_sms_gateway
from app.models.sms import VerifiedPhone
from app.repositories.alert_repository import AlertRepository
from app.repositories.sms_repository import SMSRepository
from app.schemas.alert import AlertaCreate
from app.schemas.sms import InboundSMS
from app.services.alert_service import AlertService

logger = logging.getLogger("georescue.sms")
BASE32_ID_PATTERN = re.compile(r"^[A-Z2-7]{10}$")
PHONE_PATTERN = re.compile(r"^\+[1-9][0-9]{7,14}$")


@dataclass(frozen=True)
class ParsedSignedSMS:
    client_alert_id: str
    kind: str
    latitude: float
    longitude: float
    precision_m: int
    location_age_seconds: int
    timestamp: int
    severity: int
    signed_text: str
    signature: str


class SMSService:
    ACK_MESSAGE = "Recibimos tu alerta. Si estás en peligro llama al 105/116/106."

    def __init__(self, db: Session):
        self.db = db
        self.sms_repo = SMSRepository(db)
        self.alert_repo = AlertRepository(db)
        self.alert_service = AlertService(db)
        self.gateway = create_sms_gateway()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _fernet() -> Fernet:
        key = settings.SMS_DEVICE_ENCRYPTION_KEY
        if not key:
            raise RuntimeError("SMS_DEVICE_ENCRYPTION_KEY no está configurada.")
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("SMS_DEVICE_ENCRYPTION_KEY debe ser una clave Fernet válida.") from exc

    @staticmethod
    def _otp_hash(code: str, salt: str) -> str:
        if not settings.SMS_OTP_PEPPER:
            raise RuntimeError("SMS_OTP_PEPPER no está configurado.")
        return hmac.new(
            settings.SMS_OTP_PEPPER.encode("utf-8"),
            f"{salt}:{code}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def solicitar_otp(self, username: str, phone: str) -> Dict[str, str]:
        if not PHONE_PATTERN.fullmatch(phone):
            raise ValueError("El teléfono debe estar en formato E.164.")
        owner = self.sms_repo.get_verified_phone(phone)
        if owner and owner.usuario != username:
            raise ValueError("El teléfono ya está asociado a otra cuenta.")
        now = self._now()
        if not self._reserve_outbound(phone, now):
            raise ValueError("Se alcanzó el límite temporal de SMS para este teléfono.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_hex(16)
        code_hash = self._otp_hash(code, salt)
        self.sms_repo.create_otp_challenge(username, phone, code_hash, salt, now)
        result = self.gateway.enviar(phone, f"Código GEORESCUE: {code}. Vigencia 10 min.")
        if result.get("estado") == "NO_CONFIGURADO":
            raise RuntimeError("El gateway SMS no está configurado para entregar el OTP.")
        return {"estado": "SOLICITADO", "expira_en": (now + timedelta(minutes=10)).isoformat()}

    def verificar_otp(self, username: str, phone: str, code: str) -> Dict[str, Any]:
        now = self._now()
        challenge = self.sms_repo.get_latest_otp_challenge(username, phone)
        if not challenge or challenge.consumido_en is not None:
            raise ValueError("No hay un OTP activo para este teléfono.")
        if challenge.expira_en <= now:
            challenge.consumido_en = now
            self.sms_repo.save_challenge(challenge)
            raise ValueError("El OTP expiró; solicita uno nuevo.")
        if challenge.intentos >= 3:
            challenge.consumido_en = now
            self.sms_repo.save_challenge(challenge)
            raise ValueError("Se agotaron los tres intentos permitidos.")
        expected = challenge.code_hash
        supplied = self._otp_hash(code, challenge.salt)
        if not hmac.compare_digest(expected, supplied):
            challenge.intentos += 1
            if challenge.intentos >= 3:
                challenge.consumido_en = now
            self.sms_repo.save_challenge(challenge)
            raise ValueError("El código OTP no es válido.")
        challenge.consumido_en = now
        self.sms_repo.save_challenge(challenge)
        verified = self.sms_repo.verify_phone(username, phone, now)
        return {
            "telefono": verified.telefono,
            "verificado_en": verified.verificado_en,
            "activo": verified.activo,
        }

    def registrar_dispositivo(self, username: str, device_id: str) -> Dict[str, str]:
        verified_phone = self.db.query(VerifiedPhone).filter(
            VerifiedPhone.usuario == username,
            VerifiedPhone.activo.is_(True),
        ).first()
        if not verified_phone:
            raise ValueError("Verifica primero un teléfono con OTP.")
        raw_secret = secrets.token_bytes(32)
        secret = base64.urlsafe_b64encode(raw_secret).decode("ascii").rstrip("=")
        encrypted = self._fernet().encrypt(raw_secret).decode("ascii")
        device = self.sms_repo.add_device(username, device_id, encrypted)
        return {
            "dispositivo_id": device.dispositivo_id,
            "secreto": secret,
            "aviso": "Guarda el secreto ahora; no volverá a mostrarse.",
        }

    def revocar_dispositivo(self, username: str, device_id: str) -> bool:
        return self.sms_repo.revoke_device(username, device_id, self._now())

    @staticmethod
    def parse_signed_message(message: str) -> ParsedSignedSMS:
        if not message.isascii() or len(message.encode("ascii")) > 160:
            raise ValueError("El SMS debe contener solo ASCII.")
        normalized = message.replace("\r", "").replace("\n", "").strip()
        fields = [field.strip().upper() for field in normalized.split("|")]
        if len(fields) != 10 or fields[0] != "GR1":
            raise ValueError("Formato GR1 inválido.")
        client_alert_id, kind = fields[1], fields[2]
        if not BASE32_ID_PATTERN.fullmatch(client_alert_id):
            raise ValueError("Identificador Base32 inválido.")
        if kind not in {"A", "M", "C", "U"}:
            raise ValueError("Tipo de mensaje inválido.")
        if not re.fullmatch(r"-?[0-9]{1,3}\.[0-9]{5}", fields[3]):
            raise ValueError("Latitud inválida.")
        if not re.fullmatch(r"-?[0-9]{1,3}\.[0-9]{5}", fields[4]):
            raise ValueError("Longitud inválida.")
        if not all(re.fullmatch(r"[0-9]+", value) for value in fields[5:9]):
            raise ValueError("Los campos de precisión, edad, tiempo y gravedad deben ser enteros.")
        latitude = float(fields[3])
        longitude = float(fields[4])
        precision = int(fields[5])
        age = int(fields[6])
        timestamp = int(fields[7])
        severity = int(fields[8])
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Coordenadas fuera de rango.")
        if precision > 100000 or age > 31536000 or not 1 <= severity <= 5:
            raise ValueError("Precisión, antigüedad o gravedad fuera de rango.")
        if not re.fullmatch(r"[A-Z2-7]{8}", fields[9]):
            raise ValueError("Firma Base32 inválida.")
        signed_text = "|".join(fields[:9])
        return ParsedSignedSMS(
            client_alert_id=client_alert_id,
            kind=kind,
            latitude=latitude,
            longitude=longitude,
            precision_m=precision,
            location_age_seconds=age,
            timestamp=timestamp,
            severity=severity,
            signed_text=signed_text,
            signature=fields[9],
        )

    @staticmethod
    def sign_message(unsigned_message: str, raw_secret: bytes) -> str:
        normalized = "|".join(
            part.strip().upper()
            for part in unsigned_message.replace("\r", "").replace("\n", "").strip().split("|")
        )
        digest = hmac.new(raw_secret, normalized.encode("ascii"), hashlib.sha256).digest()
        return base64.b32encode(digest).decode("ascii").rstrip("=")[:8]

    def _decode_device_secret(self, encrypted: str) -> bytes:
        try:
            return self._fernet().decrypt(encrypted.encode("ascii"))
        except (InvalidToken, UnicodeEncodeError) as exc:
            logger.error("No se pudo descifrar un secreto de dispositivo activo.")
            raise RuntimeError("No se pudo validar el secreto de un dispositivo.") from exc

    def _verify_device_signature(
        self,
        username: str,
        message: ParsedSignedSMS,
    ) -> Optional[str]:
        matching_device: Optional[str] = None
        for device in self.sms_repo.get_active_devices(username):
            secret = self._decode_device_secret(device.secreto_cifrado)
            expected = self.sign_message(message.signed_text, secret)
            if hmac.compare_digest(expected, message.signature):
                matching_device = device.dispositivo_id
        return matching_device

    def _reserve_outbound(self, phone: str, now: datetime) -> bool:
        return self.sms_repo.reserve_outbound_slot(
            phone,
            now,
            settings.SMS_OUTBOUND_LIMIT_COUNT,
            settings.SMS_OUTBOUND_LIMIT_WINDOW_SECONDS,
        )

    def procesar_webhook(
        self,
        url: str,
        headers: Dict[str, str],
        raw_body: bytes,
        content_type: str,
    ) -> Dict[str, Any]:
        if len(raw_body) > 4096:
            self.sms_repo.record_discard("", "", "SMS_ILEGIBLE", self._now())
            return {"aceptado": False, "resultado": "SMS_ILEGIBLE"}
        now = self._now()
        if not self.gateway.validar_firma_webhook(url, headers, raw_body, content_type):
            sender, text = self._extract_untrusted_body(raw_body, content_type)
            self.sms_repo.record_discard(sender, text, "FIRMA_PROVEEDOR_INVALIDA", now)
            return {"aceptado": False, "resultado": "FIRMA_PROVEEDOR_INVALIDA"}

        try:
            payload = self._parse_webhook_body(raw_body, content_type)
        except (ValueError, TypeError, json.JSONDecodeError):
            sender, text = self._extract_untrusted_body(raw_body, content_type)
            self.sms_repo.record_discard(sender, text, "SMS_ILEGIBLE", now)
            return {"aceptado": False, "resultado": "SMS_ILEGIBLE"}

        phone = payload.remitente.strip()
        verified_phone = self.sms_repo.get_alert_phone_owner(phone)
        if not verified_phone:
            self.sms_repo.record_discard(phone, payload.texto, "TELEFONO_NO_VERIFICADO", now)
            return {"aceptado": False, "resultado": "TELEFONO_NO_VERIFICADO"}

        try:
            parsed = self.parse_signed_message(payload.texto)
        except ValueError:
            self.sms_repo.record_discard(phone, payload.texto, "SMS_ILEGIBLE", now)
            return {"aceptado": False, "resultado": "SMS_ILEGIBLE"}

        if abs(int(now.timestamp()) - parsed.timestamp) > settings.SMS_TIMESTAMP_WINDOW_SECONDS:
            self.sms_repo.record_discard(phone, payload.texto, "TIMESTAMP_FUERA_DE_VENTANA", now)
            return {"aceptado": False, "resultado": "TIMESTAMP_FUERA_DE_VENTANA"}

        device_id = self._verify_device_signature(verified_phone.usuario, parsed)
        if not device_id:
            self.sms_repo.record_discard(phone, payload.texto, "FIRMA_DISPOSITIVO_INVALIDA", now)
            return {"aceptado": False, "resultado": "FIRMA_DISPOSITIVO_INVALIDA"}

        alert_id: Optional[int] = None
        if parsed.kind in {"A", "M"}:
            origin = (
                OrigenAlerta.AUTOMATICO_INERCIA.value
                if parsed.kind == "A"
                else OrigenAlerta.MANUAL.value
            )
            confirmation = (
                EstadoConfirmacion.EXPIRADO_INCONSCIENTE.value
                if parsed.kind == "A"
                else EstadoConfirmacion.CONFIRMADO.value
            )
            request = AlertaCreate(
                client_alert_id=parsed.client_alert_id,
                dispositivo_id=device_id,
                usuario=verified_phone.usuario,
                tipo_emergencia=TipoEmergencia.SISMO_INERCIAL.value,
                nivel_gravedad=parsed.severity,
                latitud=parsed.latitude,
                longitud=parsed.longitude,
                origen_alerta=origin,
                estado_confirmacion=confirmation,
                timestamp_dispositivo=datetime.fromtimestamp(parsed.timestamp, timezone.utc).replace(tzinfo=None),
                precision_m=parsed.precision_m,
                edad_lectura_s=parsed.location_age_seconds,
            )
            response = self.alert_service.despachar_alerta(request, canal_entrada="SMS")
            alert_id = response.alerta_id
        else:
            existing = self.alert_repo.get_alert_by_client_id_for_user(
                parsed.client_alert_id,
                verified_phone.usuario,
            )
            if not existing:
                self.sms_repo.record_discard(phone, payload.texto, "ALERTA_NO_ENCONTRADA", now)
                return {"aceptado": False, "resultado": "ALERTA_NO_ENCONTRADA"}
            if parsed.kind == "U":
                updated = self.alert_service.actualizar_ubicacion_sms(
                    parsed.client_alert_id,
                    verified_phone.usuario,
                    parsed.latitude,
                    parsed.longitude,
                    parsed.precision_m,
                    parsed.location_age_seconds,
                )
                alert_id = updated.id
            else:
                cancelled = self.alert_service.cancelar_alerta_sms(
                    parsed.client_alert_id,
                    verified_phone.usuario,
                    actor=f"sms:{phone}",
                )
                alert_id = cancelled.id

        reply_status = self._reply_to_sender(phone, now, parsed.kind)
        return {
            "aceptado": True,
            "alerta_id": alert_id,
            "client_alert_id": parsed.client_alert_id,
            "resultado": "ALERTA_REGISTRADA",
            "respuesta_sms": reply_status,
        }

    def _reply_to_sender(self, phone: str, now: datetime, kind: str) -> str:
        if not self._reserve_outbound(phone, now):
            return "LIMITADA"
        message = self.ACK_MESSAGE
        if kind == "C":
            message = "Recibimos tu cancelación. Si sigues en peligro llama al 105/116/106."
        elif kind == "U":
            message = "Recibimos la actualización de ubicación."
        try:
            result = self.gateway.enviar(phone, message)
        except RuntimeError:
            logger.exception("Falló el envío del SMS de respuesta; la alerta ya quedó persistida.")
            return "FALLO"
        status = result.get("estado")
        if status == "NO_CONFIGURADO":
            return "NO_CONFIGURADO"
        if status == "MOSTRADO_EN_CONSOLA":
            return "SOLO_CONSOLA_DESARROLLO"
        return "ACEPTADA_POR_PROVEEDOR"

    @staticmethod
    def _parse_webhook_body(raw_body: bytes, content_type: str) -> InboundSMS:
        if "application/x-www-form-urlencoded" in content_type.lower():
            values = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
            sender = (values.get("remitente") or values.get("From") or [""])[0]
            text = (values.get("texto") or values.get("Body") or [""])[0]
            received_at = (values.get("recibido_en") or [""])[0]
            payload: Dict[str, Any] = {"remitente": sender, "texto": text}
            if received_at:
                payload["recibido_en"] = received_at
            return InboundSMS.model_validate(payload)
        return InboundSMS.model_validate_json(raw_body)

    @staticmethod
    def _extract_untrusted_body(raw_body: bytes, content_type: str) -> tuple[str, str]:
        try:
            if "application/x-www-form-urlencoded" in content_type.lower():
                values = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
                sender = (values.get("remitente") or values.get("From") or [""])[0]
                text = (values.get("texto") or values.get("Body") or [""])[0]
            else:
                values = json.loads(raw_body.decode("utf-8"))
                sender = str(values.get("remitente", ""))
                text = str(values.get("texto", ""))
            return sender[:40], text[:2000]
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
            return "", ""

    def listar_descartados(self, limit: int = 100) -> list[Any]:
        return self.sms_repo.list_discarded(max(1, min(limit, 500)))
