"""Pruebas de extremo a extremo contra PostgreSQL + PostGIS reales.

El resto de la suite usa SQLite en memoria y no puede ejercitar las tablas con
geometría (alertas, evidencias antirrobo). Estas pruebas cubren ese hueco:
recorren por HTTP los flujos completos sobre una base PostGIS de verdad.

Se omiten salvo que se pidan de forma explícita. En PowerShell:

    $env:GEORESCUE_TEST_POSTGIS = "1"
    python -m pytest tests/test_postgis_integracion.py -v

Usan las credenciales del .env y una base APARTE llamada `<DB_NAME>_test`, que
se crea sola y cuyas tablas se VACÍAN antes de cada prueba. Nunca tocan la base
de desarrollo: el nombre debe terminar en `_test` o la suite se niega a correr.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time

import pytest

if os.environ.get("GEORESCUE_TEST_POSTGIS", "").lower() not in {"1", "true", "yes", "on"}:
    pytest.skip(
        "Pruebas PostGIS omitidas: define GEORESCUE_TEST_POSTGIS=1 para ejecutarlas.",
        allow_module_level=True,
    )

import psycopg2
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from main import app
from app.core.config import settings
from app.db.base import Base
from app.db.esquema import ESQUEMA_INICIAL, aplicar_migraciones, columnas_faltantes, ejecutar_archivo_sql
from app.infrastructure.database.session import get_db
from app.services.realtime import institutional_alert_hub

API = "/api/v1"
NOMBRE_BASE = f"{settings.DB_NAME}_test"
CLAVE_PROPIETARIO = "ClaveDePropietario#2026"
CAJAMARCA = (-7.16370, -78.50030)
LIMA = (-12.04640, -77.04280)
# JPEG mínimo: basta la firma del formato para la validación de evidencia.
FOTO_JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 60 + b"\xff\xd9").decode()


@pytest.fixture(scope="module")
def engine():
    assert NOMBRE_BASE.endswith("_test"), "La base de pruebas debe terminar en _test."
    conexion = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
        password=settings.DB_PASSWORD, dbname="postgres",
    )
    conexion.autocommit = True
    with conexion.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (NOMBRE_BASE,))
        if not cursor.fetchone():
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(NOMBRE_BASE)))
    conexion.close()

    url = (
        f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{NOMBRE_BASE}"
    )
    engine = create_engine(url)
    with engine.begin() as conexion:
        conexion.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
    # Mismo camino que scripts/preparar_bd.py: así las migraciones también quedan probadas.
    if "usuarios" not in __import__("sqlalchemy").inspect(engine).get_table_names():
        nombre, correcto, detalle = ejecutar_archivo_sql(engine, ESQUEMA_INICIAL)
        assert correcto, f"{nombre}: {detalle}"
    Base.metadata.create_all(bind=engine)
    for nombre, correcto, detalle in aplicar_migraciones(engine):
        assert correcto, f"{nombre}: {detalle}"
    assert columnas_faltantes(engine) == {}
    yield engine
    engine.dispose()


@pytest.fixture()
def api(engine, monkeypatch):
    tablas = ", ".join(f'"{nombre}"' for nombre in Base.metadata.tables)
    with engine.begin() as conexion:
        conexion.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
    Session = sessionmaker(bind=engine, autoflush=False)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(settings, "SMTP_HOST", "")
    app.dependency_overrides[get_db] = _get_db
    yield Flujo(TestClient(app), engine)
    app.dependency_overrides.pop(get_db, None)


class Flujo:
    """Atajos para escribir los flujos como los haría un usuario por HTTP."""

    def __init__(self, client, engine):
        self.client = client
        self.engine = engine
        self._owner = None
        self._ruc = 20100000000

    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}

    def ciudadano(self, usuario, password="clave1234"):
        respuesta = self.client.post(f"{API}/auth/registro/", json={"usuario": usuario, "password": password})
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()

    def propietario(self):
        if self._owner:
            return self._owner
        login = self.client.post(f"{API}/admin/login", json={"access_key": "admin"})
        assert login.status_code == 200, login.text
        cambio = self.client.post(
            f"{API}/admin/change-password",
            headers=self.auth(login.json()["access_token"]),
            json={"current_password": "admin", "new_password": CLAVE_PROPIETARIO},
        )
        self._owner = cambio.json()["access_token"]
        return self._owner

    def institucion(self, nombre, director, cobertura=None, radio_km=15):
        """Registra, aprueba y (opcionalmente) valida la cobertura. Devuelve (token, id)."""
        self._ruc += 1
        registro = self.client.post(f"{API}/auth/registro/", json={
            "usuario": director, "password": "ClaveSegura2026", "modo": "institucional",
            "nombre_institucion": nombre, "ruc_institucion": str(self._ruc),
            "tipo_institucion": "Bomberos", "region_institucion": "Cajamarca",
            "correo_institucional": "contacto@institucion.gob.pe",
            "contacto_institucional": "Ana Torres", "telefono_institucional": "976123456",
            "evidencia_institucional_url": "https://www.gob.pe/bomberos",
        })
        assert registro.status_code == 201, registro.text
        owner = self.propietario()
        solicitudes = self.client.get(f"{API}/admin/institution-applications", headers=self.auth(owner)).json()
        solicitud = next(item for item in solicitudes if item["institution_name"] == nombre)
        aprobacion = self.client.post(
            f"{API}/admin/institution-applications/{solicitud['id']}/approve",
            headers=self.auth(owner),
            json={"verification_source": "https://www.gob.pe/bomberos", "review_notes": "RUC y directorio oficial coinciden."},
        )
        assert aprobacion.status_code == 200, aprobacion.text
        instituciones = self.client.get(f"{API}/admin/institutions", headers=self.auth(owner)).json()
        institucion_id = next(item["id"] for item in instituciones if item["institution_name"] == nombre)
        if cobertura:
            validacion = self.client.put(
                f"{API}/admin/institutions/{institucion_id}/coverage",
                headers=self.auth(owner),
                json={"latitud": cobertura[0], "longitud": cobertura[1], "radio_km": radio_km,
                      "evidencia": "Resolución de jurisdicción revisada por el propietario."},
            )
            assert validacion.status_code == 200, validacion.text
        login = self.client.post(f"{API}/auth/login/", json={
            "usuario": director, "password": "ClaveSegura2026", "modo": "institucional",
        })
        assert login.status_code == 200, login.text
        return login.json()["token"], institucion_id

    def alerta(self, token, punto=CAJAMARCA, **cambios):
        cuerpo = {"tipo_emergencia": "Alerta SOS Manual", "nivel_gravedad": 4}
        if punto:
            cuerpo.update(latitud=punto[0], longitud=punto[1])
        cuerpo.update(cambios)
        respuesta = self.client.post(f"{API}/alertas/despachar/", headers=self.auth(token), json=cuerpo)
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()

    def bandeja(self, token):
        respuesta = self.client.get(f"{API}/alertas/activas/", headers=self.auth(token))
        assert respuesta.status_code == 200, respuesta.text
        return respuesta.json()

    def contar(self, consulta, **parametros):
        with self.engine.connect() as conexion:
            return conexion.execute(text(consulta), parametros).scalar()


# =============================================================================
# Asignación institucional por cobertura validada
# =============================================================================
def test_alerta_dentro_de_la_cobertura_aparece_solo_en_la_bandeja_que_corresponde(api):
    bomberos, _ = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    pnp_lima, _ = api.institucion("PNP Lima", "director_pnp", cobertura=LIMA)
    sin_cobertura, _ = api.institucion("Serenazgo Baños del Inca", "director_ser")
    ana = api.ciudadano("ana")

    alerta = api.alerta(ana["token"], CAJAMARCA)

    assert alerta["enrutamiento_institucional"]["estado"] == "EN_BANDEJA_INSTITUCIONAL"
    assert alerta["enrutamiento_institucional"]["instituciones"] == ["Bomberos Cajamarca"]
    en_bandeja = api.bandeja(bomberos)
    assert [item["id"] for item in en_bandeja] == [alerta["alerta_id"]]
    assert en_bandeja[0]["latitud"] == pytest.approx(CAJAMARCA[0])
    assert en_bandeja[0]["longitud"] == pytest.approx(CAJAMARCA[1])
    assert en_bandeja[0]["estado"] == "REGISTRADA"
    # Aislamiento: ni la institución de otra zona ni la que no tiene cobertura validada la ven.
    assert api.bandeja(pnp_lima) == []
    assert api.bandeja(sin_cobertura) == []


def test_alerta_fuera_de_toda_cobertura_no_se_asigna_y_queda_para_el_propietario(api):
    bomberos, _ = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA, radio_km=5)
    ana = api.ciudadano("ana")

    lejos = api.alerta(ana["token"], (-7.60000, -78.50030))  # ~48 km al sur del centro

    assert lejos["enrutamiento_institucional"]["estado"] == "SIN_COBERTURA_CONFIRMADA"
    assert lejos["enrutamiento_institucional"]["instituciones"] == []
    assert api.bandeja(bomberos) == []
    pendientes = api.client.get(f"{API}/admin/alerts/unassigned", headers=api.auth(api.propietario())).json()
    assert [item["id"] for item in pendientes] == [lejos["alerta_id"]]
    assert pendientes[0]["instituciones_en_cobertura"] == []


def test_un_simulacro_nunca_llega_a_una_institucion(api):
    bomberos, _ = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    ana = api.ciudadano("ana")

    simulacro = api.alerta(ana["token"], CAJAMARCA, es_simulacro=True)

    assert simulacro["enrutamiento_institucional"]["instituciones"] == []
    assert api.bandeja(bomberos) == []
    pendientes = api.client.get(f"{API}/admin/alerts/unassigned", headers=api.auth(api.propietario())).json()
    assert pendientes == []


def test_alerta_sin_ubicacion_se_asigna_a_mano_y_queda_auditada(api):
    bomberos, _ = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    ana = api.ciudadano("ana")
    owner = api.propietario()

    sin_gps = api.alerta(ana["token"], punto=None)
    assert sin_gps["enrutamiento_institucional"]["estado"] == "SIN_COBERTURA_CONFIRMADA"
    assert api.bandeja(bomberos) == []

    inexistente = api.client.post(
        f"{API}/admin/alerts/{sin_gps['alerta_id']}/assign", headers=api.auth(owner),
        json={"institution_name": "Institución Fantasma", "reason": "Prueba de institución inexistente."},
    )
    assert inexistente.status_code == 404
    ciudadano = api.client.post(
        f"{API}/admin/alerts/{sin_gps['alerta_id']}/assign", headers=api.auth(ana["token"]),
        json={"institution_name": "Bomberos Cajamarca", "reason": "Un ciudadano no puede asignar."},
    )
    assert ciudadano.status_code == 403

    asignacion = api.client.post(
        f"{API}/admin/alerts/{sin_gps['alerta_id']}/assign", headers=api.auth(owner),
        json={"institution_name": "Bomberos Cajamarca", "reason": "El ciudadano llamó y confirmó que está en Cajamarca."},
    )
    assert asignacion.status_code == 200, asignacion.text
    assert asignacion.json()["instituciones"] == ["Bomberos Cajamarca"]
    assert [item["id"] for item in api.bandeja(bomberos)] == [sin_gps["alerta_id"]]
    assert api.contar(
        "SELECT count(*) FROM alert_state_history WHERE alert_id = :id AND reason LIKE 'Asignación manual a Bomberos Cajamarca%'",
        id=sin_gps["alerta_id"],
    ) == 1
    # Repetir la asignación no duplica ni la bandeja ni la auditoría.
    api.client.post(
        f"{API}/admin/alerts/{sin_gps['alerta_id']}/assign", headers=api.auth(owner),
        json={"institution_name": "Bomberos Cajamarca", "reason": "Segundo clic sobre el mismo botón."},
    )
    assert api.contar("SELECT count(*) FROM alert_recipients WHERE alert_id = :id", id=sin_gps["alerta_id"]) == 1


def test_solo_la_institucion_asignada_cambia_el_estado_y_en_el_orden_permitido(api):
    bomberos, _ = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    pnp_lima, _ = api.institucion("PNP Lima", "director_pnp", cobertura=LIMA)
    ana = api.ciudadano("ana")
    alerta_id = api.alerta(ana["token"], CAJAMARCA)["alerta_id"]

    def cambiar(token, estado):
        return api.client.patch(f"{API}/alertas/{alerta_id}/estado/", headers=api.auth(token), json={"estado": estado})

    assert cambiar(pnp_lima, "RECIBIDA").status_code == 403       # no es su alerta
    assert cambiar(bomberos, "ATENDIDA").status_code == 403       # no se salta pasos
    assert cambiar(bomberos, "RECIBIDA").json()["estado"] == "RECIBIDA"
    assert cambiar(ana["token"], "CANCELADA").status_code == 403  # ya fue recibida
    assert cambiar(bomberos, "EN_ATENCION").json()["estado"] == "EN_ATENCION"
    assert cambiar(bomberos, "ATENDIDA").json()["estado"] == "ATENDIDA"
    assert api.bandeja(bomberos) == []  # cerrada: sale de la bandeja de abiertas
    assert api.contar("SELECT count(*) FROM alert_state_history WHERE alert_id = :id", id=alerta_id) == 4


def test_retirar_la_cobertura_deja_de_asignar_alertas_nuevas(api):
    bomberos, institucion_id = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    ana = api.ciudadano("ana")
    primera = api.alerta(ana["token"], CAJAMARCA)["alerta_id"]

    retiro = api.client.delete(f"{API}/admin/institutions/{institucion_id}/coverage", headers=api.auth(api.propietario()))
    assert retiro.status_code == 200
    assert retiro.json()["coverage_validated_at"] is None
    segunda = api.alerta(ana["token"], CAJAMARCA)

    assert segunda["enrutamiento_institucional"]["instituciones"] == []
    assert [item["id"] for item in api.bandeja(bomberos)] == [primera]  # la ya asignada se conserva


def test_la_bandeja_avisa_en_tiempo_real_a_la_institucion_asignada(api, monkeypatch):
    bomberos, _ = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    api.institucion("PNP Lima", "director_pnp", cobertura=LIMA)
    ana = api.ciudadano("ana")
    publicados = []
    publicar_original = institutional_alert_hub.publish_alert

    async def publicar_y_anotar(institucion, evento):
        publicados.append((institucion, evento))
        await publicar_original(institucion, evento)

    monkeypatch.setattr(institutional_alert_hub, "publish_alert", publicar_y_anotar)

    with api.client.websocket_connect(f"{API}/realtime/ws/alerts") as socket:
        socket.send_json({"token": bomberos})
        for _ in range(100):  # el servidor registra la conexión tras validar el token
            if institutional_alert_hub._connections.get("Bomberos Cajamarca"):
                break
            time.sleep(0.02)
        alerta = api.alerta(ana["token"], CAJAMARCA)
        evento = {"type": "alert.created", "alert_id": alerta["alerta_id"]}
        # Solo se avisa a la institución asignada, nunca a las demás.
        assert publicados == [("Bomberos Cajamarca", evento)]
        assert socket.receive_json() == evento


# =============================================================================
# Canal SMS firmado, de punta a punta
# =============================================================================
def _preparar_sms(api, monkeypatch, capsys, usuario_token, telefono="+51987654321"):
    """OTP -> verificación -> registro del dispositivo. Devuelve el secreto HMAC en bytes."""
    monkeypatch.setattr(settings, "SMS_PROVIDER", "console")
    monkeypatch.setattr(settings, "SMS_CONSOLE_PRINT_MESSAGES", True)
    monkeypatch.setattr(settings, "SMS_WEBHOOK_SECRET", "secreto-webhook-de-prueba")
    monkeypatch.setattr(settings, "SMS_OTP_PEPPER", "pepper-de-prueba")
    monkeypatch.setattr(settings, "SMS_DEVICE_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    solicitud = api.client.post(f"{API}/telefonos/solicitar-otp", headers=api.auth(usuario_token), json={"telefono": telefono})
    assert solicitud.status_code == 200, solicitud.text
    codigo = re.search(r"Código GEORESCUE: (\d{6})", capsys.readouterr().out).group(1)
    verificacion = api.client.post(
        f"{API}/telefonos/verificar-otp", headers=api.auth(usuario_token),
        json={"telefono": telefono, "codigo": codigo},
    )
    assert verificacion.status_code == 200, verificacion.text
    registro = api.client.post(
        f"{API}/dispositivos/registrar", headers=api.auth(usuario_token), json={"dispositivo_id": "android-prueba-1"},
    )
    assert registro.status_code == 200, registro.text
    secreto = registro.json()["secreto"]
    return base64.urlsafe_b64decode(secreto + "=" * (-len(secreto) % 4))


def _enviar_sms(api, secreto, tipo, punto, alert_id="ABCDEFGHJK", remitente="+51987654321", gravedad=4):
    sin_firma = f"GR1|{alert_id}|{tipo}|{punto[0]:.5f}|{punto[1]:.5f}|5|3|{int(time.time())}|{gravedad}"
    firma = base64.b32encode(hmac.new(secreto, sin_firma.encode("ascii"), hashlib.sha256).digest()).decode("ascii").rstrip("=")[:8]
    cuerpo = json.dumps({"remitente": remitente, "texto": f"{sin_firma}|{firma}"}, separators=(",", ":")).encode("ascii")
    firma_proveedor = hmac.new(settings.SMS_WEBHOOK_SECRET.encode(), cuerpo, hashlib.sha256).hexdigest()
    return api.client.post(
        f"{API}/sms/entrante", content=cuerpo,
        headers={"Content-Type": "application/json", "X-SMS-Signature": f"sha256={firma_proveedor}"},
    )


def test_sms_firmado_crea_la_alerta_y_aparece_en_la_bandeja_institucional(api, monkeypatch, capsys):
    bomberos, _ = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    ana = api.ciudadano("ana")
    secreto = _preparar_sms(api, monkeypatch, capsys, ana["token"])

    respuesta = _enviar_sms(api, secreto, "A", CAJAMARCA)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["aceptado"] is True
    en_bandeja = api.bandeja(bomberos)
    assert len(en_bandeja) == 1
    assert en_bandeja[0]["id"] == respuesta.json()["alerta_id"]
    assert en_bandeja[0]["origen_alerta"] == "AUTOMATICO_INERCIA"
    assert en_bandeja[0]["estado_confirmacion"] == "EXPIRADO_INCONSCIENTE"
    assert en_bandeja[0]["canal_entrada"] == "SMS"
    assert en_bandeja[0]["usuario"] == "ana"
    assert en_bandeja[0]["precision_m"] == 5 and en_bandeja[0]["edad_lectura_s"] == 3
    assert en_bandeja[0]["latitud"] == pytest.approx(CAJAMARCA[0])


def test_mismo_id_por_sms_y_por_api_deja_una_sola_alerta(api, monkeypatch, capsys):
    api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    ana = api.ciudadano("ana")
    secreto = _preparar_sms(api, monkeypatch, capsys, ana["token"])
    por_sms = _enviar_sms(api, secreto, "A", CAJAMARCA).json()

    por_api = api.alerta(
        ana["token"], CAJAMARCA, client_alert_id="ABCDEFGHJK",
        tipo_emergencia="Alerta Sísmica Inercial", origen_alerta="AUTOMATICO_INERCIA",
        estado_confirmacion="EXPIRADO_INCONSCIENTE",
    )
    repetido = _enviar_sms(api, secreto, "A", CAJAMARCA)

    assert por_api["alerta_id"] == por_sms["alerta_id"]
    assert repetido.json()["alerta_id"] == por_sms["alerta_id"]
    assert api.contar("SELECT count(*) FROM alertas_emergencia") == 1
    assert api.contar("SELECT count(*) FROM alert_recipients") == 1
    assert api.contar("SELECT count(*) FROM alert_outbox") == 1
    assert api.contar("SELECT canal_entrada FROM alertas_emergencia") == "SMS"  # el primer ingreso fija el canal


def test_sms_de_actualizacion_reasigna_y_el_de_cancelacion_cierra(api, monkeypatch, capsys):
    bomberos, _ = api.institucion("Bomberos Cajamarca", "director_cbp", cobertura=CAJAMARCA)
    ana = api.ciudadano("ana")
    secreto = _preparar_sms(api, monkeypatch, capsys, ana["token"])

    # Primer SMS con la última ubicación conocida, fuera de cobertura.
    inicial = _enviar_sms(api, secreto, "A", LIMA)
    assert inicial.json()["aceptado"] is True
    assert api.bandeja(bomberos) == []
    # Llega un mejor fix: tipo U con el mismo id, ahora dentro de la cobertura.
    actualizacion = _enviar_sms(api, secreto, "U", CAJAMARCA)
    assert actualizacion.json()["aceptado"] is True
    en_bandeja = api.bandeja(bomberos)
    assert [item["id"] for item in en_bandeja] == [inicial.json()["alerta_id"]]
    assert en_bandeja[0]["latitud"] == pytest.approx(CAJAMARCA[0])
    # "Estoy bien": tipo C cancela mientras nadie la haya recibido.
    cancelacion = _enviar_sms(api, secreto, "C", CAJAMARCA)
    assert cancelacion.json()["aceptado"] is True
    assert api.bandeja(bomberos) == []
    assert api.contar("SELECT estado FROM alertas_emergencia") == "CANCELADA"
    assert api.contar("SELECT estado_confirmacion FROM alertas_emergencia") == "CANCELADO_USUARIO"


def test_sms_con_firma_falsa_o_de_un_telefono_no_verificado_no_crea_alertas(api, monkeypatch, capsys):
    ana = api.ciudadano("ana")
    secreto = _preparar_sms(api, monkeypatch, capsys, ana["token"])

    firma_falsa = _enviar_sms(api, b"\x07" * 32, "A", CAJAMARCA)
    otro_telefono = _enviar_sms(api, secreto, "A", CAJAMARCA, remitente="+51911111111")
    sin_firma_de_proveedor = api.client.post(
        f"{API}/sms/entrante", content=b'{"remitente":"+51987654321","texto":"GR1"}',
        headers={"Content-Type": "application/json"},
    )

    assert firma_falsa.json()["resultado"] == "FIRMA_DISPOSITIVO_INVALIDA"
    assert otro_telefono.json()["resultado"] == "TELEFONO_NO_VERIFICADO"
    assert sin_firma_de_proveedor.status_code == 401
    assert api.contar("SELECT count(*) FROM alertas_emergencia") == 0
    assert api.contar("SELECT count(*) FROM sms_descartados") == 3


# =============================================================================
# Red familiar sobre PostGIS
# =============================================================================
def test_buzon_familiar_recibe_la_alerta_solo_tras_invitar_por_codigo_y_aceptar(api):
    ana = api.ciudadano("ana")
    beto = api.ciudadano("beto")

    invitacion = api.client.post(
        f"{API}/familia/agregar/", headers=api.auth(ana["token"]),
        json={"codigo_invitado": beto["codigo_enlace"], "parentesco": "Hermano"},
    )
    assert invitacion.status_code == 201, invitacion.text
    antes = api.alerta(ana["token"], CAJAMARCA)
    assert antes["notificacion_familiar"]["estado"] == "SIN_VINCULOS_CON_CONSENTIMIENTO"

    aceptacion = api.client.post(
        f"{API}/familia/invitaciones/{invitacion.json()['id']}/aceptar/", headers=api.auth(beto["token"]),
    )
    assert aceptacion.status_code == 200, aceptacion.text
    despues = api.alerta(ana["token"], CAJAMARCA)

    assert despues["notificacion_familiar"]["estado"] == "DISPONIBLE_EN_BUZON"
    buzon = api.client.get(f"{API}/alertas/buzon-familiar/", headers=api.auth(beto["token"])).json()
    assert [item["id"] for item in buzon] == [despues["alerta_id"]]
    assert buzon[0]["latitud"] == pytest.approx(CAJAMARCA[0])


# =============================================================================
# Módulo antirrobo
# =============================================================================
def test_antirrobo_exige_sesion_y_no_deja_elegir_usuario_ni_correo_de_destino(api):
    ana = api.ciudadano("ana")
    cuerpo = {
        "usuario": "otra_persona", "correo_destino": "victima@example.com",
        "latitud": CAJAMARCA[0], "longitud": CAJAMARCA[1], "foto_base64": FOTO_JPEG,
    }

    anonimo = api.client.post(f"{API}/security/anti-theft-alert", json=cuerpo)
    assert anonimo.status_code == 401
    assert api.contar("SELECT count(*) FROM eventos_seguridad") == 0

    registro = api.client.post(f"{API}/security/anti-theft-alert", headers=api.auth(ana["token"]), json=cuerpo)

    assert registro.status_code == 201, registro.text
    assert registro.json()["email_enviado"] is False
    assert registro.json()["motivo_sin_correo"] == "SIN_CORREO_DE_SEGURIDAD"
    assert "No se envió correo" in registro.json()["mensaje"]
    assert api.contar("SELECT usuario FROM eventos_seguridad") == "ana"
    assert api.contar("SELECT correo_destino FROM eventos_seguridad") is None


def test_antirrobo_usa_el_correo_guardado_y_dice_la_verdad_sobre_el_envio(api, monkeypatch):
    ana = api.ciudadano("ana")
    invalido = api.client.put(f"{API}/security/contact", headers=api.auth(ana["token"]), json={"correo": "no-es-un-correo"})
    assert invalido.status_code == 422
    guardado = api.client.put(f"{API}/security/contact", headers=api.auth(ana["token"]), json={"correo": " Ana@Example.com "})
    assert guardado.json() == {"correo": "ana@example.com", "servidor_puede_enviar": False, "bloqueado_hasta": None}

    sin_smtp = api.client.post(
        f"{API}/security/anti-theft-alert", headers=api.auth(ana["token"]), json={"foto_base64": FOTO_JPEG},
    ).json()
    assert sin_smtp["email_enviado"] is False
    assert sin_smtp["motivo_sin_correo"] == "SMTP_NO_CONFIGURADO"
    assert sin_smtp["latitud"] is None and sin_smtp["mapa_url"] is None  # sin GPS no se inventa un punto

    enviados = []

    class SMTPFalso:
        def __init__(self, host, port, timeout=None):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self):
            pass

        def login(self, *_):
            pass

        def send_message(self, mensaje):
            enviados.append(mensaje)

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.prueba.local")
    monkeypatch.setattr("app.services.security_service.smtplib.SMTP", SMTPFalso)
    con_smtp = api.client.post(
        f"{API}/security/anti-theft-alert", headers=api.auth(ana["token"]),
        json={"foto_base64": FOTO_JPEG, "latitud": CAJAMARCA[0], "longitud": CAJAMARCA[1]},
    ).json()

    assert con_smtp["email_enviado"] is True
    assert con_smtp["mensaje"] == "Evidencia guardada. Se envió un correo a a***@example.com."
    assert len(enviados) == 1 and enviados[0]["To"] == "ana@example.com"
    assert "Modo antirrobo activado" in enviados[0]["Subject"]
    adjuntos = [parte for parte in enviados[0].iter_attachments()]
    assert len(adjuntos) == 1 and adjuntos[0].get_content_type() == "image/jpeg"


def test_antirrobo_rechaza_archivos_que_no_son_imagen_y_limita_la_frecuencia(api):
    ana = api.ciudadano("ana")
    beto = api.ciudadano("beto")
    no_es_imagen = "data:image/jpeg;base64," + base64.b64encode(b"<script>alert(1)</script>" * 4).decode()

    rechazo = api.client.post(
        f"{API}/security/anti-theft-alert", headers=api.auth(ana["token"]), json={"foto_base64": no_es_imagen},
    )
    assert rechazo.status_code == 400

    codigos = [
        api.client.post(
            f"{API}/security/anti-theft-alert", headers=api.auth(ana["token"]), json={"foto_base64": FOTO_JPEG},
        ).status_code
        for _ in range(11)
    ]
    assert codigos == [201] * 10 + [429]

    evidencias = api.client.get(f"{API}/security/events", headers=api.auth(ana["token"])).json()
    assert len(evidencias) == 10
    foto = api.client.get(f"{API}/security/events/{evidencias[0]['id']}/photo", headers=api.auth(ana["token"]))
    assert foto.json()["foto"] == FOTO_JPEG
    # Otra cuenta no puede ver la evidencia ajena.
    ajena = api.client.get(f"{API}/security/events/{evidencias[0]['id']}/photo", headers=api.auth(beto["token"]))
    assert ajena.status_code == 404
    assert api.client.get(f"{API}/security/events", headers=api.auth(beto["token"])).json() == []


# =============================================================================
# Evidencia automática y bloqueo del correo de seguridad
# =============================================================================
def _correo(api, token, correo):
    return api.client.put(f"{API}/security/contact", headers=api.auth(token), json={"correo": correo})


def test_un_sos_real_bloquea_el_correo_de_seguridad_y_un_simulacro_no(api):
    ana = api.ciudadano("ana")
    assert _correo(api, ana["token"], "ana@example.com").status_code == 200

    api.alerta(ana["token"], CAJAMARCA, es_simulacro=True)
    assert _correo(api, ana["token"], "ana2@example.com").status_code == 200  # el simulacro no bloquea

    api.alerta(ana["token"], CAJAMARCA)
    cambio = _correo(api, ana["token"], "ladron@example.com")
    borrado = _correo(api, ana["token"], "")

    assert cambio.status_code == 423 and borrado.status_code == 423
    estado = api.client.get(f"{API}/security/contact", headers=api.auth(ana["token"])).json()
    assert estado["correo"] == "ana2@example.com"
    assert estado["bloqueado_hasta"] is not None
    # Vencido el plazo, el correo vuelve a ser editable.
    with api.engine.begin() as conexion:
        conexion.execute(text("UPDATE usuarios SET correo_seguridad_bloqueado_hasta = now() at time zone 'utc' - interval '1 minute'"))
    assert _correo(api, ana["token"], "nuevo@example.com").status_code == 200


def test_el_panico_silencioso_y_la_evidencia_tambien_bloquean_el_correo(api):
    ana = api.ciudadano("ana")
    beto = api.ciudadano("beto")
    _correo(api, ana["token"], "ana@example.com")
    _correo(api, beto["token"], "beto@example.com")

    panico = api.client.post(f"{API}/coaccion/alertar/", headers=api.auth(ana["token"]), json={
        "client_alert_id": "0b1f4a52-6d0e-4c3c-9b1a-1f2e3d4c5b6a", "latitud": CAJAMARCA[0], "longitud": CAJAMARCA[1],
        "amenaza_detectada": True, "activar_panic_silencioso": True,
    })
    assert panico.status_code == 201, panico.text
    evidencia = api.client.post(
        f"{API}/security/anti-theft-alert", headers=api.auth(beto["token"]), json={"foto_base64": FOTO_JPEG},
    )
    assert evidencia.status_code == 201, evidencia.text

    assert _correo(api, ana["token"], "x@example.com").status_code == 423
    assert _correo(api, beto["token"], "x@example.com").status_code == 423


def test_la_evidencia_automatica_indica_que_la_provoco_y_lleva_las_coordenadas(api, monkeypatch):
    ana = api.ciudadano("ana")
    _correo(api, ana["token"], "ana@example.com")
    enviados = []

    class SMTPFalso:
        def __init__(self, *_, **__):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self):
            pass

        def login(self, *_):
            pass

        def send_message(self, mensaje):
            enviados.append(mensaje)

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.prueba.local")
    monkeypatch.setattr("app.services.security_service.smtplib.SMTP", SMTPFalso)

    def evidencia(**cuerpo):
        return api.client.post(
            f"{API}/security/anti-theft-alert", headers=api.auth(ana["token"]),
            json={"foto_base64": FOTO_JPEG, "latitud": CAJAMARCA[0], "longitud": CAJAMARCA[1], **cuerpo},
        )

    assert evidencia(tipo_evento="SOS", detalle="alerta 7").status_code == 201
    assert evidencia(tipo_evento="LLAMADA_EMERGENCIA", detalle="105").status_code == 201
    assert evidencia(tipo_evento="PANICO").status_code == 201
    assert evidencia(tipo_evento="CUALQUIER_COSA").status_code == 422
    assert evidencia(tipo_evento="SOS", detalle="<script>").status_code == 422

    asuntos = [mensaje["Subject"] for mensaje in enviados]
    assert "SOS enviado" in asuntos[0]
    assert "Llamada de emergencia al 105" in asuntos[1]
    assert "Pánico silencioso activado" in asuntos[2]
    texto = enviados[0].get_body(preferencelist=("plain",)).get_content()
    assert f"{CAJAMARCA[0]}, {CAJAMARCA[1]}" in texto and "openstreetmap.org" in texto
    assert all(mensaje["To"] == "ana@example.com" for mensaje in enviados)
    tipos = [item["tipo_evento"] for item in api.client.get(f"{API}/security/events", headers=api.auth(ana["token"])).json()]
    assert tipos == ["PANICO", "LLAMADA_EMERGENCIA:105", "SOS:alerta 7"]
