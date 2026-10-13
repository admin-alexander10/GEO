from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.schemas.coaccion import RoboCoaccionCreate
from app.services.coaccion import despachar_robo_coaccion


@patch("app.services.coaccion_service.AlertRepository")
def test_despachar_robo_coaccion_does_not_claim_unconfirmed_dispatch(mock_alert_repo):
    # El servicio ya no usa funciones sueltas de crud: trabaja con repositorios.
    mock_alert_repo.return_value.create_spatial_alert.return_value = SimpleNamespace(id=77)
    mock_alert_repo.return_value.create_spatial_alert.return_value.estado = "REGISTRADA"
    mock_alert_repo.return_value.count_family_recipients.return_value = 0
    mock_alert_repo.return_value.get_institution_recipients.return_value = []

    payload = RoboCoaccionCreate(
        client_alert_id=uuid4(),
        dispositivo_id="DEV_999",
        usuario="DEV_999",
        tipo_amenaza="coaccion",
        descripcion="Se me amenazó con armas y pidieron el celular",
        latitud=-7.1601,
        longitud=-78.5102,
        amenaza_detectada=True,
        activar_panic_silencioso=True,
    )

    response = despachar_robo_coaccion(object(), payload)

    assert response.alerta_id == 77
    assert response.tipo_emergencia == "ROBO_ASALTO_COACCION"
    assert response.coordenadas == {"lat": -7.1601, "lng": -78.5102}
    assert response.alerta_silenciosa is True
    assert response.institucion_prioritaria is None
    assert response.notificacion_familiar["familiares_alertados"] == []
    assert response.recurso_asignado is None

    _, kwargs = mock_alert_repo.return_value.create_spatial_alert.call_args
    assert kwargs["tipo_emergencia"] == "ROBO_ASALTO_COACCION"
    assert kwargs["origen_alerta"] == "PANIC_SILENCIOSO"
    assert kwargs["client_alert_id"] == str(payload.client_alert_id)
