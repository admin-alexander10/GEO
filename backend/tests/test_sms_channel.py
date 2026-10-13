import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlencode

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.domain.enums import EstadoConfirmacion, OrigenAlerta, TipoEmergencia
from app.infrastructure.gateways.sms_gateway import ConsoleSMSGateway, TwilioSMSGateway
from app.models.alert import AlertStateHistory
from app.repositories.alert_repository import AlertRepository
from app.schemas.sms import InboundSMS
from app.schemas.alert import AlertaCreate
from app.services.sms_service import SMSService
from main import app

PHONE = "+51987654321"
DEVICE_ID = "android-test-1"
CLIENT_ALERT_ID = "ABCDEFGHJK"


def signed_text(kind="A", timestamp=None, client_alert_id=CLIENT_ALERT_ID):
    timestamp = timestamp or int(datetime.now(timezone.utc).timestamp())
    prefix = (
        f"GR1|{client_alert_id}|{kind}|-12.04640|-77.04280|5|3|"
        f"{timestamp}|4"
    )
    return prefix + "|" + SMSService.sign_message(prefix, b"\x01" * 32)


def service_with_mocks(monkeypatch, kind="A", timestamp=None):
    encryption_key = Fernet.generate_key()
    monkeypatch.setattr(settings, "SMS_DEVICE_ENCRYPTION_KEY", encryption_key.decode("ascii"))
    monkeypatch.setattr(settings, "SMS_OTP_PEPPER", "test-otp-pepper")
    monkeypatch.setattr(settings, "SMS_TIMESTAMP_WINDOW_SECONDS", 86400)
    service = SMSService(MagicMock())
    service.sms_repo = MagicMock()
    service.alert_repo = MagicMock()
    service.alert_service = MagicMock()
    service.gateway = MagicMock()
    service.gateway.validar_firma_webhook.return_value = True
    service.gateway.enviar.return_value = {"estado": "queued"}
    service.sms_repo.get_alert_phone_owner.return_value = SimpleNamespace(usuario="alice")
    encrypted = Fernet(encryption_key).encrypt(b"\x01" * 32).decode("ascii")
    service.sms_repo.get_active_devices.return_value = [
        SimpleNamespace(dispositivo_id=DEVICE_ID, secreto_cifrado=encrypted)
    ]
    service.sms_repo.reserve_outbound_slot.return_value = True
    timestamp = timestamp or int(datetime.now(timezone.utc).timestamp())
    raw_body = json.dumps({
        "remitente": PHONE,
        "texto": signed_text(kind, timestamp),
    }).encode("ascii")
    return service, raw_body


def test_signed_type_a_uses_existing_enums_and_alert_service(monkeypatch):
    service, raw_body = service_with_mocks(monkeypatch)
    service.alert_service.despachar_alerta.return_value = SimpleNamespace(alerta_id=42)

    result = service.procesar_webhook(
        "https://example.test/api/v1/sms/entrante",
        {},
        raw_body,
        "application/json",
    )

    assert result["aceptado"] is True
    assert result["alerta_id"] == 42
    request, = service.alert_service.despachar_alerta.call_args.args
    assert request.tipo_emergencia == TipoEmergencia.SISMO_INERCIAL.value
    assert request.origen_alerta == OrigenAlerta.AUTOMATICO_INERCIA.value
    assert request.estado_confirmacion == EstadoConfirmacion.EXPIRADO_INCONSCIENTE.value
    assert request.client_alert_id == CLIENT_ALERT_ID
    assert request.precision_m == 5
    assert request.edad_lectura_s == 3
    assert service.alert_service.despachar_alerta.call_args.kwargs == {"canal_entrada": "SMS"}


def test_signed_type_m_creates_manual_alert(monkeypatch):
    service, raw_body = service_with_mocks(monkeypatch, kind="M")
    service.alert_service.despachar_alerta.return_value = SimpleNamespace(alerta_id=43)

    result = service.procesar_webhook("https://example.test/sms", {}, raw_body, "application/json")

    request, = service.alert_service.despachar_alerta.call_args.args
    assert result["alerta_id"] == 43
    assert request.origen_alerta == OrigenAlerta.MANUAL.value
    assert request.estado_confirmacion == EstadoConfirmacion.CONFIRMADO.value


def test_invalid_device_signature_is_discarded_without_creating_alert(monkeypatch):
    service, raw_body = service_with_mocks(monkeypatch)
    service.sms_repo.get_active_devices.return_value = [
        SimpleNamespace(
            dispositivo_id=DEVICE_ID,
            secreto_cifrado=Fernet(settings.SMS_DEVICE_ENCRYPTION_KEY.encode()).encrypt(b"\x02" * 32).decode(),
        )
    ]

    result = service.procesar_webhook("https://example.test/sms", {}, raw_body, "application/json")

    assert result["resultado"] == "FIRMA_DISPOSITIVO_INVALIDA"
    service.sms_repo.record_discard.assert_called_once()
    service.alert_service.despachar_alerta.assert_not_called()


def test_unverified_phone_is_discarded_before_alert_creation(monkeypatch):
    service, raw_body = service_with_mocks(monkeypatch)
    service.sms_repo.get_alert_phone_owner.return_value = None

    result = service.procesar_webhook("https://example.test/sms", {}, raw_body, "application/json")

    assert result["resultado"] == "TELEFONO_NO_VERIFICADO"
    service.sms_repo.record_discard.assert_called_once()
    service.sms_repo.get_active_devices.assert_not_called()


def test_timestamp_outside_configured_window_is_discarded(monkeypatch):
    stale = int(datetime.now(timezone.utc).timestamp()) - 86401
    service, raw_body = service_with_mocks(monkeypatch, timestamp=stale)

    result = service.procesar_webhook("https://example.test/sms", {}, raw_body, "application/json")

    assert result["resultado"] == "TIMESTAMP_FUERA_DE_VENTANA"
    service.sms_repo.record_discard.assert_called_once()
    service.alert_service.despachar_alerta.assert_not_called()


@pytest.mark.parametrize(
    ("kind", "method_name"),
    [("U", "actualizar_ubicacion_sms"), ("C", "cancelar_alerta_sms")],
)
def test_location_update_and_cancellation_use_same_alert_id(monkeypatch, kind, method_name):
    service, raw_body = service_with_mocks(monkeypatch, kind=kind)
    service.alert_repo.get_alert_by_client_id_for_user.return_value = SimpleNamespace(id=44)
    getattr(service.alert_service, method_name).return_value = SimpleNamespace(id=44)

    result = service.procesar_webhook("https://example.test/sms", {}, raw_body, "application/json")

    assert result["alerta_id"] == 44
    assert getattr(service.alert_service, method_name).call_args.args[0] == CLIENT_ALERT_ID
    assert getattr(service.alert_service, method_name).call_args.args[1] == "alice"
    if kind == "U":
        assert service.alert_service.actualizar_ubicacion_sms.call_args.args[2:] == (
            -12.0464,
            -77.0428,
            5,
            3,
        )
    else:
        assert service.alert_service.cancelar_alerta_sms.call_args.kwargs["actor"] == f"sms:{PHONE}"


def test_ill_formed_message_from_verified_phone_is_marked_sms_ilegible(monkeypatch):
    service, raw_body = service_with_mocks(monkeypatch)
    raw_body = json.dumps({"remitente": PHONE, "texto": "no es un SMS GR1"}).encode("ascii")

    result = service.procesar_webhook("https://example.test/sms", {}, raw_body, "application/json")

    assert result["resultado"] == "SMS_ILEGIBLE"
    assert service.sms_repo.record_discard.call_args.args[2] == "SMS_ILEGIBLE"
    service.alert_service.despachar_alerta.assert_not_called()


def test_parser_accepts_whitespace_case_and_line_breaks():
    unsigned = f"gr1|{CLIENT_ALERT_ID.lower()}|a|-12.04640|-77.04280|5|3|1234567890|4"
    signature = SMSService.sign_message(unsigned, b"\x01" * 32).lower()
    parsed = SMSService.parse_signed_message(f"  {unsigned}|{signature}\r\n")

    assert parsed.client_alert_id == CLIENT_ALERT_ID
    assert parsed.kind == "A"
    assert parsed.signed_text == unsigned.upper()


def test_contract_known_hmac_vector():
    unsigned = "GR1|ABCDEFGHJK|A|-12.04640|-77.04280|5|3|1791500000|4"

    assert SMSService.sign_message(unsigned, bytes(range(32))) == "TRGS6IS7"


def test_console_webhook_signature_is_required_and_constant_format(monkeypatch):
    monkeypatch.setattr(settings, "SMS_WEBHOOK_SECRET", "provider-test-secret")
    body = b'{"remitente":"+51987654321","texto":"sms"}'
    signature = hmac.new(b"provider-test-secret", body, hashlib.sha256).hexdigest()
    gateway = ConsoleSMSGateway()

    assert gateway.validar_firma_webhook(
        "https://example.test/sms",
        {"X-SMS-Signature": f"sha256={signature}"},
        body,
        "application/json",
    )
    assert not gateway.validar_firma_webhook(
        "https://example.test/sms",
        {"X-SMS-Signature": "0" * 64},
        body,
        "application/json",
    )


def test_twilio_form_webhook_uses_twilio_signature_formula(monkeypatch):
    auth_token = "test-twilio-auth-token"
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", auth_token)
    url = "https://api.example.test/api/v1/sms/entrante"
    params = {"From": PHONE, "Body": "GR1|test", "MessageSid": "SM123"}
    body = urlencode(params).encode("ascii")
    signed = url + "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(auth_token.encode(), signed.encode(), hashlib.sha1).digest()
    signature = base64.b64encode(digest).decode("ascii")

    assert TwilioSMSGateway().validar_firma_webhook(
        url,
        {"X-Twilio-Signature": signature},
        body,
        "application/x-www-form-urlencoded",
    )


def test_invalid_provider_signature_is_discarded(monkeypatch):
    service, raw_body = service_with_mocks(monkeypatch)
    service.gateway.validar_firma_webhook.return_value = False

    result = service.procesar_webhook(
        "https://example.test/sms",
        {},
        raw_body,
        "application/json",
    )

    assert result["resultado"] == "FIRMA_PROVEEDOR_INVALIDA"
    assert service.sms_repo.record_discard.call_args.args[2] == "FIRMA_PROVEEDOR_INVALIDA"
    service.alert_service.despachar_alerta.assert_not_called()


def test_phone_otp_request_stores_only_hash_before_sending(monkeypatch):
    monkeypatch.setattr(settings, "SMS_OTP_PEPPER", "pepper-for-tests")
    monkeypatch.setattr(SMSService, "_now", staticmethod(lambda: datetime(2026, 10, 9, 12)))
    monkeypatch.setattr("app.services.sms_service.secrets.randbelow", lambda _limit: 123456)
    monkeypatch.setattr("app.services.sms_service.secrets.token_hex", lambda _length: "ab" * 16)
    service = SMSService(MagicMock())
    service.sms_repo = MagicMock()
    service.sms_repo.get_verified_phone.return_value = None
    service.sms_repo.reserve_outbound_slot.return_value = True
    service.gateway = MagicMock()
    service.gateway.enviar.return_value = {"estado": "queued"}

    response = service.solicitar_otp("alice", PHONE)

    saved = service.sms_repo.create_otp_challenge.call_args.args
    assert saved[2] == service._otp_hash("123456", "ab" * 16)
    assert "123456" in service.gateway.enviar.call_args.args[1]
    assert saved[2] != "123456"
    assert response["estado"] == "SOLICITADO"


def test_device_secret_is_returned_once_and_stored_encrypted(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "SMS_DEVICE_ENCRYPTION_KEY", key.decode("ascii"))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(usuario="alice", activo=True)
    service = SMSService(db)
    service.sms_repo = MagicMock()
    service.sms_repo.add_device.side_effect = lambda username, device_id, encrypted: SimpleNamespace(
        dispositivo_id=device_id,
        secreto_cifrado=encrypted,
    )

    response = service.registrar_dispositivo("alice", DEVICE_ID)

    raw_secret = base64.urlsafe_b64decode(response["secreto"] + "=" * (-len(response["secreto"]) % 4))
    encrypted = service.sms_repo.add_device.call_args.args[2]
    assert len(raw_secret) == 32
    assert Fernet(key).decrypt(encrypted.encode("ascii")) == raw_secret
    assert response["aviso"] == "Guarda el secreto ahora; no volverá a mostrarse."


def test_otp_verification_success_stores_phone_only_after_matching_hash(monkeypatch):
    now = datetime(2026, 10, 9, 12, 0, 0)
    monkeypatch.setattr(SMSService, "_now", staticmethod(lambda: now))
    monkeypatch.setattr(settings, "SMS_OTP_PEPPER", "pepper-for-tests")
    service = SMSService(MagicMock())
    challenge = SimpleNamespace(
        expira_en=now + timedelta(minutes=10),
        consumido_en=None,
        intentos=0,
        code_hash=service._otp_hash("123456", "salt"),
        salt="salt",
    )
    service.sms_repo = MagicMock()
    service.sms_repo.get_latest_otp_challenge.return_value = challenge
    service.sms_repo.verify_phone.return_value = SimpleNamespace(
        telefono=PHONE,
        verificado_en=now,
        activo=True,
    )

    result = service.verificar_otp("alice", PHONE, "123456")

    assert result["telefono"] == PHONE
    assert challenge.consumido_en == now
    service.sms_repo.verify_phone.assert_called_once_with("alice", PHONE, now)


def test_otp_expiration_and_three_attempt_limit(monkeypatch):
    now = datetime(2026, 10, 9, 12, 0, 0)
    monkeypatch.setattr(SMSService, "_now", staticmethod(lambda: now))
    monkeypatch.setattr(settings, "SMS_OTP_PEPPER", "pepper-for-tests")
    service = SMSService(MagicMock())
    service.sms_repo = MagicMock()
    expired = SimpleNamespace(
        expira_en=now - timedelta(seconds=1),
        consumido_en=None,
        intentos=0,
        code_hash="not-matching",
        salt="salt",
    )
    service.sms_repo.get_latest_otp_challenge.return_value = expired
    with pytest.raises(ValueError, match="expiró"):
        service.verificar_otp("alice", PHONE, "123456")
    assert expired.consumido_en == now

    active = SimpleNamespace(
        expira_en=now + timedelta(minutes=10),
        consumido_en=None,
        intentos=0,
        code_hash="not-matching",
        salt="salt",
    )
    service.sms_repo.get_latest_otp_challenge.return_value = active
    for attempt in range(3):
        with pytest.raises(ValueError, match="no es válido"):
            service.verificar_otp("alice", PHONE, "000000")
        assert active.intentos == attempt + 1
    assert active.consumido_en == now
    assert service.sms_repo.save_challenge.call_count == 4


def test_api_and_sms_ingress_can_share_short_id_without_duplicate_insert():
    existing = SimpleNamespace(
        client_alert_id=CLIENT_ALERT_ID,
        usuario="alice",
        tipo_emergencia=TipoEmergencia.SISMO_INERCIAL.value,
        nivel_gravedad=4,
        latitud=-12.0464,
        longitud=-77.0428,
        origen_alerta=OrigenAlerta.AUTOMATICO_INERCIA.value,
        estado_confirmacion=EstadoConfirmacion.EXPIRADO_INCONSCIENTE.value,
        canal_entrada="API",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing

    result = AlertRepository(db).create_spatial_alert(
        dispositivo_id="otro-dispositivo",  # No reemplaza el primer registro en un reintento.
        usuario="alice",
        tipo_emergencia=TipoEmergencia.SISMO_INERCIAL.value,
        nivel_gravedad=4,
        latitud=-12.0464,
        longitud=-77.0428,
        origen_alerta=OrigenAlerta.AUTOMATICO_INERCIA.value,
        estado_confirmacion=EstadoConfirmacion.EXPIRADO_INCONSCIENTE.value,
        client_alert_id=CLIENT_ALERT_ID,
        canal_entrada="SMS",
    )

    assert result is existing
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_sms_cancel_persists_confirmation_and_append_only_history():
    alert = SimpleNamespace(
        id=12,
        client_alert_id=CLIENT_ALERT_ID,
        usuario="alice",
        estado="REGISTRADA",
        estado_confirmacion=EstadoConfirmacion.EXPIRADO_INCONSCIENTE.value,
    )

    class Query:
        def filter(self, *_args):
            return self

        def with_for_update(self):
            return self

        def first(self):
            return alert

    class Session:
        def __init__(self):
            self.added = []
            self.committed = False

        def query(self, _model):
            return Query()

        def add(self, entity):
            self.added.append(entity)

        def commit(self):
            self.committed = True

        def refresh(self, _entity):
            return None

    db = Session()
    result = AlertRepository(db).cancel_sms_alert(CLIENT_ALERT_ID, "alice", f"sms:{PHONE}")

    history = next(entity for entity in db.added if isinstance(entity, AlertStateHistory))
    assert result.estado == "CANCELADA"
    assert result.estado_confirmacion == EstadoConfirmacion.CANCELADO_USUARIO.value
    assert history.from_state == "REGISTRADA"
    assert history.to_state == "CANCELADA"
    assert history.actor == f"sms:{PHONE}"
    assert db.committed


def test_alert_create_keeps_uuid_contract_and_accepts_optional_compact_id():
    from uuid import uuid4

    uuid_payload = AlertaCreate(client_alert_id=uuid4())
    compact_payload = AlertaCreate(client_alert_id=CLIENT_ALERT_ID)
    no_id_payload = AlertaCreate()

    assert uuid_payload.client_alert_id is not None
    assert compact_payload.client_alert_id == CLIENT_ALERT_ID
    assert no_id_payload.client_alert_id is None


def test_inbound_sms_schema_keeps_timestamp_optional_for_provider_webhooks():
    payload = InboundSMS(remitente=PHONE, texto="message")

    assert payload.recibido_en is None


def test_additive_sms_routes_are_registered_without_replacing_alert_routes():
    paths = set(app.openapi()["paths"])

    assert "/api/v1/sms/entrante" in paths
    assert "/api/v1/telefonos/solicitar-otp" in paths
    assert "/api/v1/telefonos/verificar-otp" in paths
    assert "/api/v1/dispositivos/registrar" in paths
    assert "/api/v1/alertas/despachar/" in paths
