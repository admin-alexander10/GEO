"""Pruebas de extremo a extremo (HTTP) de los flujos principales de GEORESCUE IA.

Cada prueba levanta la aplicación FastAPI real con una base SQLite en memoria, así que
no necesita PostgreSQL ni PostGIS y no toca la base de datos de desarrollo.

Ejecutar desde la carpeta backend/:

    python -m pytest tests/test_flujos_e2e.py -v

Cobertura (identificadores CP-xx para el informe de pruebas):
    CP-01..07  Registro e inicio de sesión del ciudadano
    CP-08..12  Acceso del propietario (clave temporal `admin` y cambio obligatorio)
    CP-13..24  Registro institucional, revisión del propietario, invitaciones y roles
    CP-25..34  Planes y pagos
    CP-35      Red familiar
    CP-36..40  Pago reportado por el usuario (Yape / Plin / transferencia)
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from app.core.config import settings
from app.db.base import Base
from app.infrastructure.database.session import get_db
from app.models.subscription import InstitutionAccount, InstitutionApplication, UserSubscription
from app.models.user import Usuario

API = "/api/v1"
# Las tablas con columnas PostGIS no existen en SQLite; estos flujos no las usan.
TABLAS_POSTGIS = {"alertas_emergencia", "eventos_seguridad"}
CLAVE_ADMIN_NUEVA = "ClaveDePropietario#2026"


class BaseE2E(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(
            self.engine,
            tables=[t for name, t in Base.metadata.tables.items() if name not in TABLAS_POSTGIS],
        )
        self.Session = sessionmaker(bind=self.engine, autoflush=False)

        def _get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()

    # ------------------------------ ayudantes ------------------------------
    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def mensaje(response):
        """Texto de error tal como lo vería el usuario (dominio usa `mensaje`, FastAPI usa `detail`)."""
        body = response.json()
        return body.get("mensaje") or body.get("detail")

    def registrar_ciudadano(self, usuario="juan_perez", password="clave1234"):
        return self.client.post(f"{API}/auth/registro/", json={"usuario": usuario, "password": password})

    def login(self, usuario, password, modo="familiar"):
        return self.client.post(
            f"{API}/auth/login/", json={"usuario": usuario, "password": password, "modo": modo}
        )

    def token_ciudadano(self, usuario="juan_perez", password="clave1234"):
        self.registrar_ciudadano(usuario, password)
        return self.login(usuario, password).json()["token"]

    def datos_institucion(self, **cambios):
        datos = {
            "usuario": "director_pnp",
            "password": "ClaveSegura2026",
            "modo": "institucional",
            "nombre_institucion": "Policia Nacional del Peru",
            "ruc_institucion": "20123456788",
            "tipo_institucion": "Policia",
            "region_institucion": "Cajamarca",
            "correo_institucional": "contacto@institucion.gob.pe",
            "contacto_institucional": "Ana Torres",
            "telefono_institucional": "976123456",
            "evidencia_institucional_url": "https://www.gob.pe/pnp",
        }
        datos.update(cambios)
        return datos

    def registrar_institucion(self, **cambios):
        return self.client.post(f"{API}/auth/registro/", json=self.datos_institucion(**cambios))

    def token_propietario(self):
        """Primer ingreso con `admin` + cambio obligatorio de contraseña."""
        login = self.client.post(f"{API}/admin/login", json={"access_key": "admin"})
        if login.status_code == 200:
            cambio = self.client.post(
                f"{API}/admin/change-password",
                headers=self.auth(login.json()["access_token"]),
                json={"current_password": "admin", "new_password": CLAVE_ADMIN_NUEVA},
            )
            return cambio.json()["access_token"]
        login = self.client.post(f"{API}/admin/login", json={"access_key": CLAVE_ADMIN_NUEVA})
        return login.json()["access_token"]

    def solicitud_pendiente(self, owner_token, institucion):
        items = self.client.get(
            f"{API}/admin/institution-applications", headers=self.auth(owner_token)
        ).json()
        return next(item for item in items if item["institution_name"] == institucion)

    def aprobar(self, owner_token, institucion, fuente="https://www.gob.pe/pnp"):
        solicitud = self.solicitud_pendiente(owner_token, institucion)
        return self.client.post(
            f"{API}/admin/institution-applications/{solicitud['id']}/approve",
            headers=self.auth(owner_token),
            json={"verification_source": fuente, "review_notes": "RUC y directorio oficial coinciden."},
        )

    def rechazar(self, owner_token, institucion):
        solicitud = self.solicitud_pendiente(owner_token, institucion)
        return self.client.post(
            f"{API}/admin/institution-applications/{solicitud['id']}/reject",
            headers=self.auth(owner_token),
            json={"review_notes": "No se pudo verificar el RUC declarado."},
        )

    def token_director_aprobado(self, **cambios):
        datos = self.datos_institucion(**cambios)
        self.registrar_institucion(**cambios)
        self.aprobar(self.token_propietario(), datos["nombre_institucion"])
        return self.login(datos["usuario"], datos["password"], "institucional").json()["token"]


# =============================================================================
# CP-01..07  Ciudadano
# =============================================================================
class TestCiudadano(BaseE2E):
    def test_cp01_registro_ciudadano_crea_cuenta_individual_con_token(self):
        r = self.registrar_ciudadano()
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["rol"], "ciudadano")
        self.assertEqual(body["institucion"], "individual")
        self.assertTrue(body["token"])
        self.assertTrue(body["codigo_enlace"].startswith("GEO-"))

    def test_cp02_login_ciudadano_correcto_y_sesion_verificable(self):
        self.registrar_ciudadano()
        r = self.login("juan_perez", "clave1234")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rol"], "ciudadano")
        me = self.client.get(f"{API}/auth/me/", headers=self.auth(r.json()["token"]))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["usuario"], "juan_perez")
        self.assertNotIn("institution:view", me.json()["permisos"])

    def test_cp03_clave_incorrecta_devuelve_401_con_mensaje_legible(self):
        self.registrar_ciudadano()
        r = self.login("juan_perez", "otra-clave")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.mensaje(r), "Usuario o contraseña incorrectos.")
        # Un usuario inexistente responde igual: no se revela qué cuentas existen.
        r = self.login("no_existe", "otra-clave")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.mensaje(r), "Usuario o contraseña incorrectos.")

    def test_cp04_usuario_duplicado_es_rechazado(self):
        self.registrar_ciudadano()
        r = self.registrar_ciudadano(password="distinta123")
        self.assertEqual(r.status_code, 400)
        self.assertIn("ya está registrado", self.mensaje(r))

    def test_cp05_registro_publico_no_puede_autoasignarse_rol_institucional(self):
        r = self.client.post(f"{API}/auth/registro/", json={
            "usuario": "intruso", "password": "clave1234", "rol": "director", "institucion": "COER Cajamarca",
        })
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["rol"], "ciudadano")
        self.assertEqual(r.json()["institucion"], "individual")

    def test_cp06_ciudadano_no_entra_por_el_acceso_institucional(self):
        self.registrar_ciudadano()
        r = self.login("juan_perez", "clave1234", "institucional")
        self.assertEqual(r.status_code, 401)
        self.assertIn("pestaña 'Familiar'", self.mensaje(r))

    def test_cp07_sin_token_o_con_token_alterado_no_hay_sesion(self):
        token = self.token_ciudadano()
        self.assertEqual(self.client.get(f"{API}/auth/me/").status_code, 401)
        alterado = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        self.assertEqual(self.client.get(f"{API}/auth/me/", headers=self.auth(alterado)).status_code, 401)

    def test_cp07b_datos_invalidos_devuelven_422_con_el_campo(self):
        r = self.client.post(f"{API}/auth/registro/", json={"usuario": "ab", "password": "1"})
        self.assertEqual(r.status_code, 422)
        campos = {item["loc"][-1] for item in r.json()["detail"]}
        self.assertEqual(campos, {"usuario", "password"})


# =============================================================================
# CP-08..12  Propietario de la plataforma (admin)
# =============================================================================
class TestPropietario(BaseE2E):
    def test_cp08_primer_ingreso_solo_acepta_la_clave_temporal_admin(self):
        mala = self.client.post(f"{API}/admin/login", json={"access_key": "otra"})
        self.assertEqual(mala.status_code, 401)
        ok = self.client.post(f"{API}/admin/login", json={"access_key": "admin"})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["must_change_password"])
        self.assertEqual(ok.json()["expires_in"], 7200)

    def test_cp09_no_puede_revisar_solicitudes_sin_cambiar_la_clave(self):
        token = self.client.post(f"{API}/admin/login", json={"access_key": "admin"}).json()["access_token"]
        r = self.client.get(f"{API}/admin/institution-applications", headers=self.auth(token))
        self.assertEqual(r.status_code, 403)
        self.assertIn("Cambia la contraseña", self.mensaje(r))
        r = self.client.get(f"{API}/admin/payments", headers=self.auth(token))
        self.assertEqual(r.status_code, 403)

    def test_cp10_cambio_de_clave_valida_longitud_y_que_no_sea_la_temporal(self):
        token = self.client.post(f"{API}/admin/login", json={"access_key": "admin"}).json()["access_token"]
        url = f"{API}/admin/change-password"
        corta = self.client.post(url, headers=self.auth(token), json={"current_password": "admin", "new_password": "corta"})
        self.assertEqual(corta.status_code, 422)
        actual_mala = self.client.post(url, headers=self.auth(token), json={"current_password": "no-es", "new_password": CLAVE_ADMIN_NUEVA})
        self.assertEqual(actual_mala.status_code, 401)
        ok = self.client.post(url, headers=self.auth(token), json={"current_password": "admin", "new_password": CLAVE_ADMIN_NUEVA})
        self.assertEqual(ok.status_code, 200)
        self.assertFalse(ok.json()["must_change_password"])
        lista = self.client.get(f"{API}/admin/institution-applications", headers=self.auth(ok.json()["access_token"]))
        self.assertEqual(lista.status_code, 200)

    def test_cp11_tras_el_cambio_admin_deja_de_funcionar(self):
        self.token_propietario()
        vieja = self.client.post(f"{API}/admin/login", json={"access_key": "admin"})
        self.assertEqual(vieja.status_code, 401)
        nueva = self.client.post(f"{API}/admin/login", json={"access_key": CLAVE_ADMIN_NUEVA})
        self.assertEqual(nueva.status_code, 200)
        self.assertFalse(nueva.json()["must_change_password"])

    def test_cp12_un_ciudadano_o_un_anonimo_no_entran_al_panel(self):
        self.token_propietario()
        ciudadano = self.token_ciudadano()
        url = f"{API}/admin/institution-applications"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, headers=self.auth(ciudadano)).status_code, 403)


# =============================================================================
# CP-13..24  Flujo institucional
# =============================================================================
class TestFlujoInstitucional(BaseE2E):
    def test_cp13_registro_institucional_crea_director_pendiente_no_ciudadano(self):
        r = self.registrar_institucion()
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.json()["token"])  # no hay sesión hasta la aprobación
        self.assertEqual(r.json()["rol"], "director")
        with self.Session() as db:
            cuenta = db.query(Usuario).filter(Usuario.usuario == "director_pnp").one()
            institucion = db.query(InstitutionAccount).one()
            solicitud = db.query(InstitutionApplication).one()
        self.assertEqual(cuenta.rol, "director")
        self.assertEqual(cuenta.institucion, "Policia Nacional del Peru")
        self.assertEqual(cuenta.is_active, 0)
        self.assertFalse(institucion.is_active)
        self.assertEqual(solicitud.status, "pending")
        self.assertEqual(solicitud.ruc, "20123456788")

    def test_cp14_registro_institucional_incompleto_es_rechazado(self):
        r = self.registrar_institucion(ruc_institucion=None)
        self.assertEqual(r.status_code, 400)
        self.assertIn("RUC", self.mensaje(r))
        r = self.registrar_institucion(ruc_institucion="123")
        self.assertEqual(r.status_code, 422)
        r = self.registrar_institucion(evidencia_institucional_url="http://www.gob.pe/pnp")
        self.assertEqual(r.status_code, 400)
        self.assertIn("HTTPS", self.mensaje(r))
        with self.Session() as db:
            self.assertEqual(db.query(Usuario).count(), 0)

    def test_cp15_login_antes_de_la_aprobacion_explica_que_esta_pendiente(self):
        self.registrar_institucion()
        r = self.login("director_pnp", "ClaveSegura2026", "institucional")
        self.assertEqual(r.status_code, 403)
        self.assertIn("pendiente de revisión", self.mensaje(r))
        # Con la contraseña equivocada no se revela el estado de la solicitud.
        r = self.login("director_pnp", "equivocada", "institucional")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.mensaje(r), "Usuario o contraseña incorrectos.")

    def test_cp16_aprobacion_exige_fuente_gob_pe_y_habilita_el_login_institucional(self):
        self.registrar_institucion()
        owner = self.token_propietario()
        solicitud = self.solicitud_pendiente(owner, "Policia Nacional del Peru")
        self.assertEqual(solicitud["applicant_username"], "director_pnp")

        falsa = self.aprobar(owner, "Policia Nacional del Peru", fuente="https://gob.pe.sitio-falso.com/pnp")
        self.assertEqual(falsa.status_code, 422)
        sin_https = self.aprobar(owner, "Policia Nacional del Peru", fuente="http://www.gob.pe/pnp")
        self.assertEqual(sin_https.status_code, 422)

        ok = self.aprobar(owner, "Policia Nacional del Peru")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["status"], "approved")
        self.assertEqual(ok.json()["reviewed_by"], "platform-owner")

        r = self.login("director_pnp", "ClaveSegura2026", "institucional")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rol"], "director")
        self.assertEqual(r.json()["institucion"], "Policia Nacional del Peru")
        self.assertIn("institution:manage", r.json()["permisos"])
        cuenta = self.client.get(f"{API}/subscriptions/institutions/me", headers=self.auth(r.json()["token"]))
        self.assertEqual(cuenta.status_code, 200)
        self.assertTrue(cuenta.json()["is_active"])

    def test_cp17_cuenta_institucional_no_entra_por_el_acceso_familiar(self):
        self.token_director_aprobado()
        r = self.login("director_pnp", "ClaveSegura2026", "familiar")
        self.assertEqual(r.status_code, 401)
        self.assertIn("pestaña 'Institucional'", self.mensaje(r))
        # Con la contraseña equivocada no se revela de qué tipo es la cuenta.
        r = self.login("director_pnp", "equivocada", "familiar")
        self.assertEqual(self.mensaje(r), "Usuario o contraseña incorrectos.")

    def test_cp18_rechazo_mantiene_todo_desactivado_y_lo_informa_al_solicitante(self):
        self.registrar_institucion()
        owner = self.token_propietario()
        r = self.rechazar(owner, "Policia Nacional del Peru")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "rejected")
        login = self.login("director_pnp", "ClaveSegura2026", "institucional")
        self.assertEqual(login.status_code, 403)
        self.assertIn("rechazada", self.mensaje(login))
        with self.Session() as db:
            self.assertFalse(db.query(InstitutionAccount).one().is_active)
            self.assertEqual(db.query(Usuario).one().is_active, 0)

    def test_cp19_institucion_o_ruc_duplicados_son_rechazados(self):
        self.registrar_institucion()
        mismo_nombre = self.registrar_institucion(usuario="otro_director", ruc_institucion="20999999999")
        self.assertEqual(mismo_nombre.status_code, 400)
        mismo_ruc = self.registrar_institucion(usuario="otro_director", nombre_institucion="Bomberos Cajamarca")
        self.assertEqual(mismo_ruc.status_code, 400)
        self.assertIn("RUC", self.mensaje(mismo_ruc))

    def test_cp20_una_solicitud_ya_revisada_no_se_puede_volver_a_decidir(self):
        self.registrar_institucion()
        owner = self.token_propietario()
        solicitud = self.solicitud_pendiente(owner, "Policia Nacional del Peru")
        self.aprobar(owner, "Policia Nacional del Peru")
        otra_vez = self.client.post(
            f"{API}/admin/institution-applications/{solicitud['id']}/reject",
            headers=self.auth(owner), json={"review_notes": "Intento de revertir la decisión."},
        )
        self.assertEqual(otra_vez.status_code, 404)
        aprobadas = self.client.get(
            f"{API}/admin/institution-applications?status_filter=approved", headers=self.auth(owner)
        ).json()
        self.assertEqual(len(aprobadas), 1)
        self.assertEqual(aprobadas[0]["verification_source"], "https://www.gob.pe/pnp")

    def test_cp21_ciudadano_que_pide_conversion_conserva_su_cuenta_hasta_la_aprobacion(self):
        self.registrar_ciudadano("maria", "clave-de-maria")
        r = self.registrar_institucion(usuario="maria", password="clave-de-maria",
                                       nombre_institucion="COER Cajamarca", ruc_institucion="20111111111")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["rol"], "ciudadano")
        # Mientras espera, sigue entrando como ciudadana (no pierde el SOS).
        self.assertEqual(self.login("maria", "clave-de-maria", "familiar").status_code, 200)
        self.assertEqual(self.login("maria", "clave-de-maria", "institucional").status_code, 401)
        # No puede abrir una segunda solicitud mientras hay una pendiente.
        segunda = self.registrar_institucion(usuario="maria", password="clave-de-maria",
                                             nombre_institucion="Otra Entidad", ruc_institucion="20222222222")
        self.assertEqual(segunda.status_code, 400)
        # Con la contraseña equivocada nadie puede pedir la conversión a nombre de otro.
        ajena = self.registrar_institucion(usuario="maria", password="no-es-la-clave",
                                           nombre_institucion="Entidad Ajena", ruc_institucion="20333333333")
        self.assertEqual(ajena.status_code, 400)

        self.assertEqual(self.aprobar(self.token_propietario(), "COER Cajamarca").status_code, 200)
        institucional = self.login("maria", "clave-de-maria", "institucional")
        self.assertEqual(institucional.status_code, 200)
        self.assertEqual(institucional.json()["rol"], "director")
        self.assertEqual(self.login("maria", "clave-de-maria", "familiar").status_code, 401)

    def test_cp21b_conversion_rechazada_deja_al_ciudadano_como_estaba(self):
        self.registrar_ciudadano("maria", "clave-de-maria")
        self.registrar_institucion(usuario="maria", password="clave-de-maria",
                                   nombre_institucion="COER Cajamarca", ruc_institucion="20111111111")
        self.rechazar(self.token_propietario(), "COER Cajamarca")
        r = self.login("maria", "clave-de-maria", "familiar")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rol"], "ciudadano")

    def test_cp22_invitacion_crea_operador_con_permisos_limitados_y_es_de_un_solo_uso(self):
        director = self.token_director_aprobado()
        invitacion = self.client.post(f"{API}/subscriptions/institutions/members", headers=self.auth(director), json={
            "institution_name": "Policia Nacional del Peru", "member_name": "Luis Rojas",
            "member_email": "luis@pnp.gob.pe", "role": "operador",
        })
        self.assertEqual(invitacion.status_code, 200)
        token_invitacion = invitacion.json()["invitation_url"].split("invite=")[1]

        aceptar = self.client.post(f"{API}/auth/invitaciones/aceptar/",
                                   json={"token": token_invitacion, "password": "ClaveDeOperador2026"})
        self.assertEqual(aceptar.status_code, 200)
        self.assertEqual(aceptar.json()["rol"], "operador")
        repetir = self.client.post(f"{API}/auth/invitaciones/aceptar/",
                                   json={"token": token_invitacion, "password": "ClaveDeOperador2026"})
        self.assertEqual(repetir.status_code, 401)

        operador = self.login("luis@pnp.gob.pe", "ClaveDeOperador2026", "institucional")
        self.assertEqual(operador.status_code, 200)
        self.assertEqual(operador.json()["institucion"], "Policia Nacional del Peru")
        token_operador = operador.json()["token"]
        # El operador ve su institución, pero no puede invitar ni cambiar el plan.
        self.assertEqual(self.client.get(f"{API}/subscriptions/institutions/me/members", headers=self.auth(token_operador)).status_code, 200)
        invitar = self.client.post(f"{API}/subscriptions/institutions/members", headers=self.auth(token_operador), json={
            "institution_name": "Policia Nacional del Peru", "member_name": "Otro", "member_email": "otro@pnp.gob.pe", "role": "operador",
        })
        self.assertEqual(invitar.status_code, 403)
        plan = self.client.put(f"{API}/subscriptions/institutions/me/plan", headers=self.auth(token_operador), json={"plan_code": "pro"})
        self.assertEqual(plan.status_code, 403)
        # Un director no puede crear otro director por invitación.
        escalar = self.client.post(f"{API}/subscriptions/institutions/members", headers=self.auth(director), json={
            "institution_name": "Policia Nacional del Peru", "member_name": "Jefe", "member_email": "jefe@pnp.gob.pe", "role": "director",
        })
        self.assertEqual(escalar.status_code, 400)

    def test_cp23_una_institucion_no_puede_ver_ni_invitar_en_otra(self):
        director_a = self.token_director_aprobado()
        director_b = self.token_director_aprobado(
            usuario="director_coer", nombre_institucion="COER Cajamarca", ruc_institucion="20111111111")
        ajena = self.client.get(f"{API}/subscriptions/institutions/COER Cajamarca/members", headers=self.auth(director_a))
        self.assertEqual(ajena.status_code, 403)
        invitar = self.client.post(f"{API}/subscriptions/institutions/members", headers=self.auth(director_a), json={
            "institution_name": "COER Cajamarca", "member_name": "Infiltrado", "member_email": "x@pnp.gob.pe", "role": "operador",
        })
        self.assertEqual(invitar.status_code, 403)
        propia = self.client.get(f"{API}/subscriptions/institutions/me", headers=self.auth(director_b))
        self.assertEqual(propia.json()["institution_name"], "COER Cajamarca")

    def test_cp24_miembro_desactivado_pierde_el_acceso_de_inmediato(self):
        director = self.token_director_aprobado()
        invitacion = self.client.post(f"{API}/subscriptions/institutions/members", headers=self.auth(director), json={
            "institution_name": "Policia Nacional del Peru", "member_name": "Luis Rojas",
            "member_email": "luis@pnp.gob.pe", "role": "operador",
        }).json()
        aceptar = self.client.post(f"{API}/auth/invitaciones/aceptar/", json={
            "token": invitacion["invitation_url"].split("invite=")[1], "password": "ClaveDeOperador2026"})
        token_operador = aceptar.json()["token"]
        miembro = self.client.get(f"{API}/subscriptions/institutions/me/members", headers=self.auth(director)).json()[0]

        baja = self.client.patch(f"{API}/subscriptions/institutions/me/members/{miembro['id']}",
                                 headers=self.auth(director), json={"is_active": False})
        self.assertEqual(baja.status_code, 200)
        # El token que ya tenía deja de servir y tampoco puede volver a iniciar sesión.
        self.assertEqual(self.client.get(f"{API}/auth/me/", headers=self.auth(token_operador)).status_code, 401)
        login = self.login("luis@pnp.gob.pe", "ClaveDeOperador2026", "institucional")
        self.assertEqual(login.status_code, 403)
        self.assertIn("desactivada", self.mensaje(login))


# =============================================================================
# CP-25..34  Planes y pagos
# =============================================================================
class TestPagos(BaseE2E):
    def mi_plan(self, token):
        return self.client.get(f"{API}/subscriptions/me", headers=self.auth(token)).json()

    def checkout(self, token, plan_code, **extra):
        return self.client.post(f"{API}/subscriptions/checkout", headers=self.auth(token),
                                json={"plan_code": plan_code, **extra})

    def pagar(self, token, plan_code="pro", metodo="yape", operacion="00123456", **extra):
        """Plan de pago con el pago reportado, como lo envía el formulario."""
        return self.checkout(token, plan_code, payment_method=metodo, payment_reference=operacion, **extra)

    def test_cp25_catalogo_de_planes_es_publico(self):
        r = self.client.get(f"{API}/subscriptions/plans")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([plan["code"] for plan in r.json()], ["free", "pro", "enterprise"])
        precios = {plan["code"]: plan["price"] for plan in r.json()}
        self.assertEqual(precios["free"], 0.0)
        self.assertEqual(precios["pro"], 39.0)  # mismo monto que muestra la tarjeta del frontend

    def test_cp26_no_se_puede_contratar_sin_iniciar_sesion(self):
        r = self.client.post(f"{API}/subscriptions/checkout", json={"usuario": "guest_user", "plan_code": "pro"})
        self.assertEqual(r.status_code, 401)
        with self.Session() as db:
            self.assertEqual(db.query(UserSubscription).count(), 0)

    def test_cp27_cuenta_nueva_esta_en_free_y_el_plan_gratuito_se_activa_al_instante(self):
        token = self.token_ciudadano()
        self.assertEqual(self.mi_plan(token)["plan_code"], "free")
        r = self.checkout(token, "free")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "active")
        self.assertIsNone(r.json()["checkout_url"])

    def test_cp28_plan_de_pago_sin_pasarela_queda_en_validacion_y_no_se_activa_solo(self):
        token = self.token_ciudadano()
        r = self.pagar(token)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "manual_review")
        self.assertTrue(r.json()["requires_manual_confirmation"])
        plan = self.mi_plan(token)
        self.assertEqual(plan["plan_code"], "free")  # aún no pagó: sigue en Free
        self.assertEqual(plan["pending_plan_code"], "pro")
        self.assertEqual(plan["pending_status"], "manual_review")
        # Repetir el envío no duplica solicitudes.
        self.pagar(token)
        with self.Session() as db:
            self.assertEqual(db.query(UserSubscription).count(), 1)

    def test_cp29_el_propietario_aprueba_el_pago_y_el_plan_se_activa(self):
        token = self.token_ciudadano()
        self.pagar(token, metodo="plin", operacion="77788899")
        owner = self.token_propietario()
        pendientes = self.client.get(f"{API}/admin/payments", headers=self.auth(owner)).json()
        self.assertEqual(len(pendientes), 1)
        self.assertEqual(pendientes[0]["usuario"], "juan_perez")
        self.assertEqual(pendientes[0]["plan_code"], "pro")
        # El propietario ve exactamente lo que debe contrastar con su cuenta.
        self.assertEqual(pendientes[0]["payment_method"], "plin")
        self.assertEqual(pendientes[0]["payment_reference"], "77788899")
        self.assertEqual(pendientes[0]["price"], 39.0)

        ok = self.client.post(f"{API}/admin/payments/{pendientes[0]['id']}/approve", headers=self.auth(owner))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["status"], "active")
        plan = self.mi_plan(token)
        self.assertEqual(plan["plan_code"], "pro")
        self.assertIsNone(plan["pending_plan_code"])
        self.assertIsNotNone(plan["expires_at"])
        # Ya revisado: no se puede aprobar dos veces.
        otra = self.client.post(f"{API}/admin/payments/{pendientes[0]['id']}/approve", headers=self.auth(owner))
        self.assertEqual(otra.status_code, 404)
        self.assertEqual(self.pagar(token).json()["message"], "Ya tienes activo el plan Pro.")

    def test_cp30_pago_rechazado_deja_al_usuario_en_su_plan_anterior(self):
        token = self.token_ciudadano()
        self.pagar(token)
        owner = self.token_propietario()
        pago = self.client.get(f"{API}/admin/payments", headers=self.auth(owner)).json()[0]
        r = self.client.post(f"{API}/admin/payments/{pago['id']}/reject", headers=self.auth(owner))
        self.assertEqual(r.json()["status"], "rejected")
        plan = self.mi_plan(token)
        self.assertEqual(plan["plan_code"], "free")
        self.assertIsNone(plan["pending_plan_code"])

    def test_cp31_nadie_puede_contratar_ni_consultar_a_nombre_de_otro(self):
        self.registrar_ciudadano("victima", "clave-victima")
        atacante = self.token_ciudadano("atacante", "clave-atacante")
        r = self.pagar(atacante, usuario="victima")
        self.assertEqual(r.json()["usuario"], "atacante")  # el titular sale del token, no del cuerpo
        ajeno = self.client.get(f"{API}/subscriptions/status/victima", headers=self.auth(atacante))
        self.assertEqual(ajeno.status_code, 403)
        self.assertEqual(self.client.get(f"{API}/subscriptions/status/victima").status_code, 401)
        # Solo el propietario valida pagos.
        self.assertEqual(self.client.get(f"{API}/admin/payments", headers=self.auth(atacante)).status_code, 403)
        self.assertEqual(self.client.post(f"{API}/admin/payments/1/approve", headers=self.auth(atacante)).status_code, 403)

    def test_cp32_planes_invalidos_para_la_cuenta_son_rechazados(self):
        ciudadano = self.token_ciudadano()
        inexistente = self.checkout(ciudadano, "gold")
        self.assertEqual(inexistente.status_code, 400)
        enterprise = self.checkout(ciudadano, "enterprise")
        self.assertEqual(enterprise.status_code, 400)
        self.assertIn("instituciones públicas", self.mensaje(enterprise))
        director = self.token_director_aprobado()
        institucional = self.checkout(director, "pro")
        self.assertEqual(institucional.status_code, 400)
        self.assertIn("panel de la institución", self.mensaje(institucional))

    def test_cp33_con_stripe_el_plan_se_activa_solo_cuando_la_pasarela_confirma_el_pago(self):
        """Stripe simulado (mock): no se llama a la pasarela real."""
        token = self.token_ciudadano()
        fake_stripe = MagicMock()
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(
            id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123")
        with patch("app.services.subscription_service.stripe", fake_stripe), \
                patch.object(settings, "STRIPE_SECRET_KEY", "sk_test_simulada"):
            r = self.checkout(token, "pro")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "pending")
            self.assertEqual(r.json()["checkout_url"], "https://checkout.stripe.com/c/pay/cs_test_123")
            enviado = fake_stripe.checkout.Session.create.call_args.kwargs
            self.assertEqual(enviado["mode"], "subscription")
            self.assertEqual(enviado["metadata"], {"usuario": "juan_perez", "plan_code": "pro"})
            self.assertIn("session_id={CHECKOUT_SESSION_ID}", enviado["success_url"])
            self.assertNotIn("customer_email", enviado)  # el usuario no es un correo real
            info = self.client.get(f"{API}/subscriptions/payment-info").json()
            self.assertEqual(info["gateway"], "stripe")  # el frontend no muestra el formulario manual

            # El usuario vuelve del checkout sin haber pagado: el plan NO se activa.
            fake_stripe.checkout.Session.retrieve.return_value = SimpleNamespace(payment_status="unpaid", customer=None)
            sin_pagar = self.client.post(f"{API}/subscriptions/checkout/confirm", headers=self.auth(token),
                                         json={"session_id": "cs_test_123"})
            self.assertEqual(sin_pagar.status_code, 200)
            self.assertEqual(sin_pagar.json()["plan_code"], "free")
            self.assertEqual(sin_pagar.json()["pending_status"], "pending")

            # Stripe confirma el pago: ahora sí.
            fake_stripe.checkout.Session.retrieve.return_value = SimpleNamespace(payment_status="paid", customer="cus_123")
            pagado = self.client.post(f"{API}/subscriptions/checkout/confirm", headers=self.auth(token),
                                      json={"session_id": "cs_test_123"})
            self.assertEqual(pagado.json()["plan_code"], "pro")
            self.assertEqual(pagado.json()["status"], "active")
            self.assertEqual(pagado.json()["provider"], "stripe")

    def test_cp34_no_se_puede_confirmar_la_sesion_de_pago_de_otro_usuario(self):
        victima = self.token_ciudadano("victima", "clave-victima")
        atacante = self.token_ciudadano("atacante", "clave-atacante")
        fake_stripe = MagicMock()
        fake_stripe.checkout.Session.create.return_value = SimpleNamespace(id="cs_test_victima", url="https://checkout.stripe.com/x")
        fake_stripe.checkout.Session.retrieve.return_value = SimpleNamespace(payment_status="paid", customer="cus_1")
        with patch("app.services.subscription_service.stripe", fake_stripe), \
                patch.object(settings, "STRIPE_SECRET_KEY", "sk_test_simulada"):
            self.checkout(victima, "pro")
            r = self.client.post(f"{API}/subscriptions/checkout/confirm", headers=self.auth(atacante),
                                 json={"session_id": "cs_test_victima"})
            self.assertEqual(r.status_code, 400)
            self.assertEqual(self.mi_plan(atacante)["plan_code"], "free")
            inventada = self.client.post(f"{API}/subscriptions/checkout/confirm", headers=self.auth(victima),
                                         json={"session_id": "cs_inventada"})
            self.assertEqual(inventada.status_code, 400)


    # ----------------------- Pago reportado por el usuario -----------------------
    def test_cp36_datos_de_cobro_son_publicos_e_indican_pago_manual(self):
        r = self.client.get(f"{API}/subscriptions/payment-info")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["gateway"], "manual")
        self.assertEqual([m["code"] for m in r.json()["methods"]], ["yape", "plin", "transferencia"])
        self.assertTrue(r.json()["account_holder"])
        self.assertTrue(all(m["destination"] for m in r.json()["methods"]))

    def test_cp37_plan_de_pago_exige_metodo_y_numero_de_operacion(self):
        token = self.token_ciudadano()
        sin_datos = self.checkout(token, "pro")
        self.assertEqual(sin_datos.status_code, 400)
        self.assertIn("método", self.mensaje(sin_datos))
        metodo_invalido = self.pagar(token, metodo="bitcoin")
        self.assertEqual(metodo_invalido.status_code, 400)
        sin_operacion = self.pagar(token, operacion="  ")
        self.assertEqual(sin_operacion.status_code, 400)
        self.assertIn("número de operación", self.mensaje(sin_operacion))
        muy_corta = self.pagar(token, operacion="12")
        self.assertEqual(muy_corta.status_code, 400)
        # Ningún intento inválido deja una solicitud registrada.
        with self.Session() as db:
            self.assertEqual(db.query(UserSubscription).count(), 0)
        self.assertIsNone(self.mi_plan(token)["pending_plan_code"])

    def test_cp38_el_pago_reportado_guarda_metodo_operacion_y_monto(self):
        token = self.token_ciudadano()
        r = self.pagar(token, metodo="Transferencia", operacion="  OP 2026  0099 ")
        self.assertEqual(r.status_code, 200)
        self.assertIn("OP 2026 0099", r.json()["message"])
        with self.Session() as db:
            fila = db.query(UserSubscription).one()
        self.assertEqual(fila.status, "manual_review")
        self.assertEqual(fila.payment_method, "transferencia")  # se normaliza a minúsculas
        self.assertEqual(fila.payment_reference, "OP 2026 0099")  # sin espacios sobrantes
        self.assertEqual(fila.price, 39.0)

    def test_cp39_un_mismo_comprobante_no_sirve_para_dos_cuentas(self):
        primero = self.token_ciudadano("ana", "clave-ana")
        segundo = self.token_ciudadano("beto", "clave-beto")
        self.assertEqual(self.pagar(primero, operacion="55554444").status_code, 200)
        repetido = self.pagar(segundo, operacion="55554444")
        self.assertEqual(repetido.status_code, 400)
        self.assertIn("ya fue registrado", self.mensaje(repetido))
        # Otro número, o el mismo número por otro medio, sí es una operación distinta.
        self.assertEqual(self.pagar(segundo, operacion="55554445").status_code, 200)
        # El dueño del comprobante puede corregir y reenviar su propia solicitud.
        self.assertEqual(self.pagar(primero, operacion="55554444").status_code, 200)

    def test_cp40_el_usuario_puede_corregir_el_numero_antes_de_la_validacion(self):
        token = self.token_ciudadano()
        self.pagar(token, operacion="11112222")
        self.pagar(token, metodo="plin", operacion="33334444")
        owner = self.token_propietario()
        pendientes = self.client.get(f"{API}/admin/payments", headers=self.auth(owner)).json()
        self.assertEqual(len(pendientes), 1)
        self.assertEqual(pendientes[0]["payment_method"], "plin")
        self.assertEqual(pendientes[0]["payment_reference"], "33334444")


# =============================================================================
# CP-35  Red familiar
# =============================================================================
class TestRedFamiliar(BaseE2E):
    def test_cp35_el_vinculo_solo_existe_tras_aceptacion_en_app(self):
        token = self.token_ciudadano()
        codigo_maria = self.registrar_ciudadano("maria", "clave-de-maria").json()["codigo_enlace"]
        # El nombre de usuario ya no sirve para invitar: hace falta el código que ella comparte.
        por_nombre = self.client.post(f"{API}/familia/agregar/", headers=self.auth(token), json={
            "usuario_invitado": "maria", "parentesco": "Madre",
        })
        self.assertEqual(por_nombre.status_code, 422)
        codigo_inexistente = self.client.post(f"{API}/familia/agregar/", headers=self.auth(token), json={
            "codigo_invitado": "GEO-000000", "parentesco": "Madre",
        })
        self.assertEqual(codigo_inexistente.status_code, 400)
        # Se acepta el código en minúsculas y con espacios alrededor.
        alta = self.client.post(f"{API}/familia/agregar/", headers=self.auth(token), json={
            "codigo_invitado": f"  {codigo_maria.lower()} ", "parentesco": "Madre",
        })
        self.assertEqual(alta.status_code, 201)
        self.assertEqual(alta.json()["estado"], "PENDIENTE")
        enviadas = self.client.get(f"{API}/familia/invitaciones/enviadas/", headers=self.auth(token))
        self.assertEqual([item["invitado_usuario"] for item in enviadas.json()], ["maria"])
        lista = self.client.get(f"{API}/familia/listar/juan_perez", headers=self.auth(token))
        self.assertEqual(lista.status_code, 200)
        self.assertEqual(lista.json(), [])

        token_maria = self.login("maria", "clave-de-maria").json()["token"]
        pendientes = self.client.get(f"{API}/familia/invitaciones/recibidas/", headers=self.auth(token_maria))
        self.assertEqual(len(pendientes.json()), 1)
        aceptacion = self.client.post(
            f"{API}/familia/invitaciones/{alta.json()['id']}/aceptar/",
            headers=self.auth(token_maria),
        )
        self.assertEqual(aceptacion.status_code, 200)
        self.assertEqual(aceptacion.json()["estado"], "ACEPTADA")

        lista = self.client.get(f"{API}/familia/listar/juan_perez", headers=self.auth(token))
        self.assertEqual(lista.json()[0]["familiar_usuario"], "maria")
        self.assertEqual(lista.json()[0]["parentesco"], "Madre")
        enviadas = self.client.get(f"{API}/familia/invitaciones/enviadas/", headers=self.auth(token))
        self.assertEqual(enviadas.json(), [])
        repetida = self.client.post(f"{API}/familia/agregar/", headers=self.auth(token), json={
            "codigo_invitado": codigo_maria, "parentesco": "Madre",
        })
        self.assertEqual(repetida.status_code, 400)
        self.assertIn("ya está en tu red", self.mensaje(repetida))

    def test_vinculo_familiar_impide_auto_invitacion_y_lectura_de_otra_cuenta(self):
        codigo_juan = self.registrar_ciudadano("juan_perez", "clave-juan").json()["codigo_enlace"]
        token_juan = self.login("juan_perez", "clave-juan").json()["token"]
        codigo_maria = self.registrar_ciudadano("maria", "clave-maria").json()["codigo_enlace"]
        auto = self.client.post(
            f"{API}/familia/agregar/",
            headers=self.auth(token_juan),
            json={"codigo_invitado": codigo_juan, "parentesco": "Yo"},
        )
        self.assertEqual(auto.status_code, 400)

        token_maria = self.login("maria", "clave-maria").json()["token"]
        invitacion = self.client.post(
            f"{API}/familia/agregar/",
            headers=self.auth(token_juan),
            json={"codigo_invitado": codigo_maria, "parentesco": "Hermana"},
        ).json()
        no_es_invitada = self.client.post(
            f"{API}/familia/invitaciones/{invitacion['id']}/aceptar/",
            headers=self.auth(token_juan),
        )
        self.assertIn(no_es_invitada.status_code, (404, 400))
        lectura_ajena = self.client.get(
            f"{API}/familia/listar/juan_perez",
            headers=self.auth(token_maria),
        )
        self.assertEqual(lectura_ajena.status_code, 403)


if __name__ == "__main__":
    unittest.main()
