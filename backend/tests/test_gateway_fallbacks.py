from app.infrastructure.gateways.notification_gateway import EmergencyNotificationGateway
from app.infrastructure.gateways.routing_gateway import EmergencyRoutingGateway
from app.schemas.rescue import RutaResponse


def test_notification_fallback_does_not_claim_family_delivery():
    result = EmergencyNotificationGateway().notify_family_members(
        familiares=["familiar_consentido"],
        tipo_emergencia="SOS",
        coordenadas={"lat": -12.0, "lng": -77.0},
        es_critico=True,
    )

    assert result["estado"] == "NO_CONFIGURADO"
    assert result["familiares_alertados"] == []
    assert result["canal"] is None


def test_notification_fallback_does_not_log_location_or_recipient(caplog):
    gateway = EmergencyNotificationGateway()
    gateway.notify_family_members(
        familiares=["persona-privada"],
        tipo_emergencia="SOS",
        coordenadas={"lat": -12.123456, "lng": -77.654321},
        es_critico=False,
    )
    gateway.dispatch_institutional_alert(
        institucion="institucion-no-asignada",
        alerta_id=7,
        tipo_emergencia="SOS",
        prioridad=5,
        coordenadas={"lat": -12.123456, "lng": -77.654321},
    )

    assert "persona-privada" not in caplog.text
    assert "institucion-no-asignada" not in caplog.text
    assert "-12.123456" not in caplog.text
    assert "-77.654321" not in caplog.text


def test_institutional_fallback_does_not_invent_coverage_or_eta():
    result = EmergencyNotificationGateway().dispatch_institutional_alert(
        institucion="institucion-no-asignada",
        alerta_id=7,
        tipo_emergencia="SOS",
        prioridad=5,
        coordenadas={"lat": -12.0, "lng": -77.0},
    )

    assert result["estado"] == "SIN_COBERTURA_CONFIRMADA"
    assert result["institucion_responsable"] is None
    assert result["tiempo_estimado_despliegue"] is None


def test_routing_fallback_returns_no_synthetic_route_or_eta():
    result = EmergencyRoutingGateway().compute_rescue_route(
        origen_lat=-12.0,
        origen_lng=-77.0,
        destino_lat=-12.1,
        destino_lng=-77.1,
        evitar_bloqueos=True,
    )
    response = RutaResponse(
        origen={"lat": -12.0, "lng": -77.0},
        destino={"lat": -12.1, "lng": -77.1},
        **result,
    )

    assert response.estado_algoritmo == "PROVEEDOR_DE_RUTAS_NO_CONFIGURADO"
    assert response.distancia_km is None
    assert response.tiempo_estimado_llegada is None
    assert response.bloqueos_evitados is None
    assert response.puntos_ruta == []
