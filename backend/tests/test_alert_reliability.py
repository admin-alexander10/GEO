from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.exceptions import IdempotencyConflictException
from app.models.alert import AlertOutbox, AlertStateHistory, AlertaEmergencia
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertaCreate
from app.services.alert_service import AlertService


def make_payload(**changes):
    payload = {
        "client_alert_id": str(uuid4()),
        "usuario": "ciudadano_1",
        "dispositivo_id": "device_1",
        "tipo_emergencia": "SOS",
        "nivel_gravedad": 4,
        "latitud": -12.0464,
        "longitud": -77.0428,
    }
    payload.update(changes)
    return AlertaCreate(**payload)


def test_alert_service_returns_only_persisted_facts():
    db_alert = SimpleNamespace(
        id=31,
        client_alert_id="a6861057-71de-4d2f-ae98-60e3554cd5bc",
        estado="REGISTRADA",
        origen_alerta="MANUAL",
        estado_confirmacion="CONFIRMADO",
        creado_en=datetime(2026, 1, 1),
    )
    with patch("app.services.alert_service.AlertRepository") as repository:
        repository.return_value.create_spatial_alert.return_value = db_alert
        repository.return_value.count_family_recipients.return_value = 0
        repository.return_value.get_institution_recipients.return_value = []
        response = AlertService(MagicMock()).despachar_alerta(make_payload())

    assert response.estado == "REGISTRADA"
    assert response.alerta_id == 31
    assert response.enrutamiento_institucional.institucion_responsable is None
    assert response.enrutamiento_institucional.tiempo_estimado_despliegue is None
    assert response.notificacion_familiar.estado == "SIN_VINCULOS_CON_CONSENTIMIENTO"
    assert response.recurso_asignado is None


def test_alert_service_propagates_persistence_failure_without_claiming_success():
    with patch("app.services.alert_service.AlertRepository") as repository:
        repository.return_value.create_spatial_alert.side_effect = RuntimeError("database unavailable")
        with pytest.raises(RuntimeError, match="database unavailable"):
            AlertService(MagicMock()).despachar_alerta(make_payload())


def test_alert_service_forwards_sms_metadata_to_existing_repository():
    alert = SimpleNamespace(
        id=32,
        client_alert_id="ABCDEFGHJK",
        estado="REGISTRADA",
        origen_alerta="AUTOMATICO_INERCIA",
        estado_confirmacion="EXPIRADO_INCONSCIENTE",
        creado_en=datetime(2026, 1, 1),
    )
    with patch("app.services.alert_service.AlertRepository") as repository:
        repository.return_value.create_spatial_alert.return_value = alert
        repository.return_value.count_family_recipients.return_value = 0
        repository.return_value.get_institution_recipients.return_value = []
        AlertService(MagicMock()).despachar_alerta(
            make_payload(
                client_alert_id="ABCDEFGHJK",
                origen_alerta="AUTOMATICO_INERCIA",
                estado_confirmacion="EXPIRADO_INCONSCIENTE",
                precision_m=5,
                edad_lectura_s=3,
            ),
            canal_entrada="SMS",
        )

    kwargs = repository.return_value.create_spatial_alert.call_args.kwargs
    assert kwargs["canal_entrada"] == "SMS"
    assert kwargs["precision_m"] == 5
    assert kwargs["edad_lectura_s"] == 3
    assert kwargs["client_alert_id"] == "ABCDEFGHJK"


def test_alert_payload_rejects_invalid_coordinates_and_missing_idempotency_key():
    with pytest.raises(ValidationError):
        make_payload(latitud=91)
    with pytest.raises(ValidationError):
        make_payload(client_alert_id="not-a-uuid")
    with pytest.raises(ValidationError):
        make_payload(longitud=None)


def test_repository_returns_exact_duplicate_without_creating_records():
    existing = SimpleNamespace(
        dispositivo_id="device_1",
        usuario="ciudadano_1",
        tipo_emergencia="SOS",
        nivel_gravedad=4,
        latitud=-12.0464,
        longitud=-77.0428,
        origen_alerta="MANUAL",
        estado_confirmacion="CONFIRMADO",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing

    result = AlertRepository(db).create_spatial_alert(
        dispositivo_id="device_1",
        usuario="ciudadano_1",
        tipo_emergencia="SOS",
        nivel_gravedad=4,
        latitud=-12.0464,
        longitud=-77.0428,
        client_alert_id="a9c28f04-60f9-4bb0-b1d4-32d6d65f80aa",
    )

    assert result is existing
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_repository_rejects_idempotency_key_reuse_with_different_payload():
    existing = SimpleNamespace(
        dispositivo_id="device_1",
        usuario="ciudadano_1",
        tipo_emergencia="SOS",
        nivel_gravedad=4,
        latitud=-12.0464,
        longitud=-77.0428,
        origen_alerta="MANUAL",
        estado_confirmacion="CONFIRMADO",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing

    with pytest.raises(IdempotencyConflictException):
        AlertRepository(db).create_spatial_alert(
            dispositivo_id="device_1",
            usuario="ciudadano_1",
            tipo_emergencia="SOS",
            nivel_gravedad=4,
            latitud=-12.0,
            longitud=-77.0428,
            client_alert_id="a9c28f04-60f9-4bb0-b1d4-32d6d65f80aa",
        )
    db.add.assert_not_called()


def test_repository_persists_alert_audit_and_outbox_in_one_transaction():
    class FakeSession:
        def __init__(self):
            self.entities = []
            self.committed = False

        def query(self, model):
            return SimpleNamespace(
                filter=lambda *_: SimpleNamespace(first=lambda: None, all=lambda: [])
            )

        def add(self, entity):
            self.entities.append(entity)

        def flush(self):
            next(entity for entity in self.entities if isinstance(entity, AlertaEmergencia)).id = 52

        def commit(self):
            assert len(self.entities) == 3
            self.committed = True

        def refresh(self, _entity):
            return None

        def rollback(self):
            raise AssertionError("rollback was not expected")

    db = FakeSession()
    alert = AlertRepository(db).create_spatial_alert(
        dispositivo_id="device_1",
        usuario="ciudadano_1",
        tipo_emergencia="SOS",
        nivel_gravedad=4,
        latitud=-12.0464,
        longitud=-77.0428,
        client_alert_id="a9c28f04-60f9-4bb0-b1d4-32d6d65f80aa",
    )

    history = next(item for item in db.entities if isinstance(item, AlertStateHistory))
    outbox = next(item for item in db.entities if isinstance(item, AlertOutbox))
    assert db.committed is True
    assert alert.id == 52
    assert history.to_state == "REGISTRADA"
    assert history.actor == "ciudadano_1"
    assert outbox.alert_id == 52
    assert outbox.status == "PENDING"
