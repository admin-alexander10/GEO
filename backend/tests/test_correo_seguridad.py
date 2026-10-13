"""Correo de seguridad: registro y bloqueo temporal tras una alerta o evidencia.

Corre sin PostgreSQL. Que el bloqueo se active solo al enviar un SOS, un pánico
o una evidencia está probado sobre PostGIS en tests/test_postgis_integracion.py.
"""
from datetime import datetime, timedelta

from app.models.user import Usuario
from tests.test_flujos_e2e import API, BaseE2E


class TestCorreoDeSeguridad(BaseE2E):
    def fijar_bloqueo(self, usuario, hasta):
        with self.Session() as db:
            db.query(Usuario).filter(Usuario.usuario == usuario).update({"correo_seguridad_bloqueado_hasta": hasta})
            db.commit()

    def guardar(self, token, correo):
        return self.client.put(f"{API}/security/contact", headers=self.auth(token), json={"correo": correo})

    def test_sin_alertas_el_correo_se_puede_guardar_cambiar_y_borrar(self):
        token = self.token_ciudadano()
        self.assertEqual(self.guardar(token, "ana@example.com").json()["correo"], "ana@example.com")
        self.assertEqual(self.guardar(token, "otra@example.com").json()["correo"], "otra@example.com")
        self.assertIsNone(self.guardar(token, "").json()["correo"])
        self.assertIsNone(self.client.get(f"{API}/security/contact", headers=self.auth(token)).json()["bloqueado_hasta"])

    def test_con_bloqueo_vigente_no_se_puede_cambiar_ni_borrar_el_correo_guardado(self):
        token = self.token_ciudadano()
        self.guardar(token, "ana@example.com")
        self.fijar_bloqueo("juan_perez", datetime.utcnow() + timedelta(hours=3))

        cambio = self.guardar(token, "ladron@example.com")
        borrado = self.guardar(token, "")
        mismo = self.guardar(token, "ana@example.com")

        self.assertEqual(cambio.status_code, 423)
        self.assertIn("bloqueado", self.mensaje(cambio))
        self.assertEqual(borrado.status_code, 423)
        self.assertEqual(mismo.status_code, 200)  # volver a guardar el mismo no cambia nada
        estado = self.client.get(f"{API}/security/contact", headers=self.auth(token)).json()
        self.assertEqual(estado["correo"], "ana@example.com")
        self.assertIsNotNone(estado["bloqueado_hasta"])

    def test_cuando_el_bloqueo_vence_el_correo_vuelve_a_ser_editable(self):
        token = self.token_ciudadano()
        self.guardar(token, "ana@example.com")
        self.fijar_bloqueo("juan_perez", datetime.utcnow() - timedelta(minutes=1))

        cambio = self.guardar(token, "nuevo@example.com")

        self.assertEqual(cambio.status_code, 200)
        self.assertEqual(cambio.json()["correo"], "nuevo@example.com")
        self.assertIsNone(cambio.json()["bloqueado_hasta"])

    def test_si_no_habia_correo_se_puede_registrar_uno_aun_con_bloqueo(self):
        token = self.token_ciudadano()
        self.fijar_bloqueo("juan_perez", datetime.utcnow() + timedelta(hours=3))
        sin_correo = self.client.get(f"{API}/security/contact", headers=self.auth(token)).json()
        self.assertIsNone(sin_correo["bloqueado_hasta"])  # no hay nada que proteger todavía

        primero = self.guardar(token, "ana@example.com")
        segundo = self.guardar(token, "otro@example.com")

        self.assertEqual(primero.status_code, 200)
        self.assertIsNotNone(primero.json()["bloqueado_hasta"])
        self.assertEqual(segundo.status_code, 423)  # una vez registrado, queda protegido

    def test_el_bloqueo_es_de_cada_cuenta(self):
        token_juan = self.token_ciudadano("juan_perez", "clave-juan")
        token_maria = self.token_ciudadano("maria", "clave-maria")
        self.guardar(token_juan, "juan@example.com")
        self.guardar(token_maria, "maria@example.com")
        self.fijar_bloqueo("juan_perez", datetime.utcnow() + timedelta(hours=3))

        self.assertEqual(self.guardar(token_juan, "x@example.com").status_code, 423)
        self.assertEqual(self.guardar(token_maria, "nueva@example.com").status_code, 200)

    def test_el_servidor_de_ejemplo_de_env_no_cuenta_como_correo_saliente(self):
        from unittest.mock import patch
        from app.core.config import settings

        token = self.token_ciudadano()
        casos = {"": False, "smtp.tu-proveedor.com": False, "smtp.gmail.com": True}
        for host, esperado in casos.items():
            with patch.object(settings, "SMTP_HOST", host):
                contacto = self.client.get(f"{API}/security/contact", headers=self.auth(token)).json()
            self.assertEqual(contacto["servidor_puede_enviar"], esperado, host)
