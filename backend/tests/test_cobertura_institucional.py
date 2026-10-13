"""Cobertura geográfica de instituciones y asignación de alertas.

Estas pruebas corren sin PostgreSQL. El recorrido completo sobre PostGIS
(alerta -> bandeja institucional) está en tests/test_postgis_integracion.py.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.geo import distancia_km
from app.models.alert import AlertRecipient, AlertaEmergencia
from app.repositories.alert_repository import AlertRepository
from tests.test_flujos_e2e import API, BaseE2E

CAJAMARCA = (-7.1637, -78.5003)
LIMA = (-12.0464, -77.0428)


def institucion(nombre, centro, radio_km, validada=True, activa=True):
    return SimpleNamespace(
        institution_name=nombre,
        coverage_lat=centro[0] if centro else None,
        coverage_lng=centro[1] if centro else None,
        coverage_radius_km=radio_km,
        coverage_validated_at=datetime(2026, 10, 1) if validada else None,
        is_active=activa,
    )


class SesionConInstituciones:
    """Sesión mínima: devuelve las instituciones que la consulta SQL dejaría pasar."""

    def __init__(self, instituciones):
        self.instituciones = instituciones
        self.agregados = []
        self.confirmado = False

    def query(self, modelo):
        if getattr(modelo, "__tablename__", "") == "institution_accounts":
            filas = [i for i in self.instituciones if i.is_active and i.coverage_validated_at]
        else:
            filas = []
        return SimpleNamespace(filter=lambda *_: SimpleNamespace(all=lambda: filas, first=lambda: None))

    def add(self, entidad):
        self.agregados.append(entidad)

    def flush(self):
        next(e for e in self.agregados if isinstance(e, AlertaEmergencia)).id = 9

    def commit(self):
        self.confirmado = True

    def refresh(self, _):
        return None

    def rollback(self):
        raise AssertionError("no se esperaba rollback")


def test_distancia_haversine_coincide_con_valores_conocidos():
    assert distancia_km(*CAJAMARCA, *CAJAMARCA) == 0
    # Un grado de latitud mide ~111,2 km en cualquier longitud.
    assert distancia_km(-7.0, -78.5, -8.0, -78.5) == pytest.approx(111.2, abs=0.2)
    # Cajamarca - Lima en línea recta: ~565 km.
    assert distancia_km(*CAJAMARCA, *LIMA) == pytest.approx(565, abs=5)


def test_solo_cubren_el_punto_las_instituciones_activas_validadas_y_dentro_del_radio():
    repo = AlertRepository(SesionConInstituciones([
        institucion("Bomberos Cajamarca", CAJAMARCA, 15),
        institucion("PNP Cajamarca", CAJAMARCA, 30),
        institucion("PNP Lima", LIMA, 30),
        institucion("Cobertura sin validar", CAJAMARCA, 50, validada=False),
        institucion("Institución desactivada", CAJAMARCA, 50, activa=False),
        institucion("Validada pero sin centro", None, 50),
    ]))

    assert repo.institutions_covering(*CAJAMARCA) == ["Bomberos Cajamarca", "PNP Cajamarca"]
    # A ~20 km del centro: fuera del radio de 15 km, dentro del de 30 km.
    assert repo.institutions_covering(-7.3437, -78.5003) == ["PNP Cajamarca"]
    assert repo.institutions_covering(*LIMA) == ["PNP Lima"]
    # Sin ubicación no se asigna a nadie: no hay institución predeterminada.
    assert repo.institutions_covering(None, None) == []


def test_la_alerta_y_su_asignacion_institucional_se_guardan_en_la_misma_transaccion():
    sesion = SesionConInstituciones([institucion("Bomberos Cajamarca", CAJAMARCA, 15)])

    AlertRepository(sesion).create_spatial_alert(
        dispositivo_id="ana", usuario="ana", tipo_emergencia="SOS", nivel_gravedad=4,
        latitud=CAJAMARCA[0], longitud=CAJAMARCA[1],
    )

    destinatarios = [e for e in sesion.agregados if isinstance(e, AlertRecipient)]
    assert sesion.confirmado is True
    assert [(d.recipient_type, d.recipient_username, d.alert_id) for d in destinatarios] == [
        ("INSTITUTION", "Bomberos Cajamarca", 9),
    ]


def test_un_simulacro_no_genera_destinatarios_institucionales():
    sesion = SesionConInstituciones([institucion("Bomberos Cajamarca", CAJAMARCA, 15)])

    AlertRepository(sesion).create_spatial_alert(
        dispositivo_id="ana", usuario="ana", tipo_emergencia="SOS", nivel_gravedad=4,
        latitud=CAJAMARCA[0], longitud=CAJAMARCA[1], es_simulacro=True,
    )

    assert [e for e in sesion.agregados if isinstance(e, AlertRecipient)] == []


class TestCoberturaDesdeElPanelDelPropietario(BaseE2E):
    COBERTURA = {
        "latitud": CAJAMARCA[0], "longitud": CAJAMARCA[1], "radio_km": 15,
        "evidencia": "Resolución de jurisdicción revisada por el propietario.",
    }

    def test_el_propietario_valida_y_retira_la_cobertura_de_una_institucion_aprobada(self):
        self.token_director_aprobado()
        owner = self.token_propietario()

        instituciones = self.client.get(f"{API}/admin/institutions", headers=self.auth(owner)).json()
        self.assertEqual([i["institution_name"] for i in instituciones], ["Policia Nacional del Peru"])
        self.assertIsNone(instituciones[0]["coverage_validated_at"])

        validada = self.client.put(
            f"{API}/admin/institutions/{instituciones[0]['id']}/coverage",
            headers=self.auth(owner), json=self.COBERTURA,
        )
        self.assertEqual(validada.status_code, 200)
        self.assertEqual(validada.json()["coverage_radius_km"], 15)
        self.assertEqual(validada.json()["coverage_validated_by"], "platform-owner")
        self.assertIsNotNone(validada.json()["coverage_validated_at"])

        retirada = self.client.delete(
            f"{API}/admin/institutions/{instituciones[0]['id']}/coverage", headers=self.auth(owner),
        )
        self.assertEqual(retirada.status_code, 200)
        self.assertIsNone(retirada.json()["coverage_validated_at"])

    def test_no_hay_cobertura_para_instituciones_pendientes_ni_con_datos_invalidos(self):
        self.registrar_institucion()  # queda pendiente de aprobación
        owner = self.token_propietario()
        self.assertEqual(self.client.get(f"{API}/admin/institutions", headers=self.auth(owner)).json(), [])
        from app.models.subscription import InstitutionAccount
        with self.Session() as db:
            pendiente_id = db.query(InstitutionAccount).first().id

        pendiente = self.client.put(
            f"{API}/admin/institutions/{pendiente_id}/coverage", headers=self.auth(owner), json=self.COBERTURA,
        )
        self.assertEqual(pendiente.status_code, 404)
        for cambio in ({"radio_km": 0}, {"radio_km": 5000}, {"latitud": 95}, {"evidencia": "corta"}):
            invalida = self.client.put(
                f"{API}/admin/institutions/{pendiente_id}/coverage",
                headers=self.auth(owner), json={**self.COBERTURA, **cambio},
            )
            self.assertEqual(invalida.status_code, 422, cambio)

    def test_solo_el_propietario_administra_coberturas_y_asignaciones(self):
        director = self.token_director_aprobado()
        ciudadano = self.token_ciudadano()
        for token in (director, ciudadano):
            self.assertEqual(self.client.get(f"{API}/admin/institutions", headers=self.auth(token)).status_code, 403)
            self.assertEqual(
                self.client.put(f"{API}/admin/institutions/1/coverage", headers=self.auth(token), json=self.COBERTURA).status_code,
                403,
            )
            self.assertEqual(self.client.get(f"{API}/admin/alerts/unassigned", headers=self.auth(token)).status_code, 403)
        self.assertEqual(self.client.get(f"{API}/admin/institutions").status_code, 401)
