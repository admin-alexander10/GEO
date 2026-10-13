"""Directorio de puntos de atención locales (comisarías, bomberos, salud).

Corre sin PostgreSQL: la tabla no usa geometría, el punto más cercano lo calcula
el dispositivo del usuario.
"""
from datetime import date, timedelta

from tests.test_flujos_e2e import API, BaseE2E

HOY = date.today().isoformat()
FUENTE = "Relación oficial de comisarías descargada de gob.pe"
CSV_COMAS = (
    "tipo,nombre,telefono,latitud,longitud,direccion,distrito\n"
    "COMISARIA,Comisaría Cajamarca,(076) 362165,-7.15750,-78.51760,Jr. Del Comercio 1013,Cajamarca\n"
    "bomberos,Compañía de Bomberos Cajamarca N.° 59,076 363333,-7.16400,-78.50800,,Cajamarca\n"
    "Centro de Salud,C.S. Baños del Inca,,-7.16300,-78.46400,Av. Manco Cápac,Los Baños del Inca\n"
)


class TestDirectorioDeEmergencia(BaseE2E):
    def importar(self, csv, owner=None, **cambios):
        cuerpo = {"csv": csv, "fuente": FUENTE, "verificado_en": HOY}
        cuerpo.update(cambios)
        return self.client.post(
            f"{API}/admin/directory/import", headers=self.auth(owner or self.token_propietario()), json=cuerpo,
        )

    def directorio(self, **params):
        return self.client.get(f"{API}/directorio/emergencia", params=params).json()

    def test_importa_un_csv_y_lo_publica_sin_pedir_sesion_ni_ubicacion(self):
        resultado = self.importar(CSV_COMAS)

        self.assertEqual(resultado.status_code, 200, resultado.text)
        self.assertEqual(resultado.json()["creados"], 3)
        self.assertEqual(resultado.json()["sin_telefono"], 1)
        self.assertEqual(resultado.json()["total_rechazados"], 0)
        publico = self.directorio()
        self.assertEqual(publico["total"], 3)
        self.assertFalse(publico["sin_cambios"])
        por_nombre = {punto["nombre"]: punto for punto in publico["puntos"]}
        comisaria = por_nombre["Comisaría Cajamarca"]
        self.assertEqual(comisaria["tipo"], "COMISARIA")
        self.assertEqual(comisaria["telefono"], "(076) 362165")
        self.assertEqual(comisaria["verificado_en"], HOY)
        self.assertAlmostEqual(comisaria["latitud"], -7.1575)
        # Los tipos escritos de otra forma se reconocen; sin teléfono se guarda igual.
        self.assertEqual(por_nombre["Compañía de Bomberos Cajamarca N.° 59"]["tipo"], "BOMBEROS")
        self.assertEqual(por_nombre["C.S. Baños del Inca"]["tipo"], "SALUD")
        self.assertIsNone(por_nombre["C.S. Baños del Inca"]["telefono"])
        # La fuente interna no se expone en el directorio público.
        self.assertNotIn("fuente", comisaria)

    def test_acepta_el_formato_de_excel_en_espanol_y_un_tipo_para_todo_el_archivo(self):
        csv_excel = (
            "﻿NOMBRE_COMISARIA;TELEFONO;LAT;LON;DISTRITO\n"
            "CPNP SAN JUAN;076-123456;-7,29000;-78,49000;San Juan\n"
            "CPNP JESUS;;-7,24500;-78,38000;Jesús\n"
        )

        resultado = self.importar(csv_excel, tipo_por_defecto="COMISARIA")

        self.assertEqual(resultado.status_code, 200, resultado.text)
        self.assertEqual(resultado.json()["creados"], 2)
        puntos = {punto["nombre"]: punto for punto in self.directorio()["puntos"]}
        self.assertAlmostEqual(puntos["CPNP SAN JUAN"]["latitud"], -7.29)
        self.assertAlmostEqual(puntos["CPNP SAN JUAN"]["longitud"], -78.49)
        self.assertEqual(puntos["CPNP JESUS"]["tipo"], "COMISARIA")

    def test_la_ubicacion_aproximada_se_declara_en_el_csv_y_llega_a_la_app(self):
        csv = (
            "tipo,nombre,telefono,latitud,longitud,distrito,ubicacion_aproximada\n"
            "COMISARIA,Comisaría Namora,957-686-775,-7.2019,-78.3247,Namora,si\n"
            "SALUD,Centro de Salud Namora,,-7.2019,-78.3247,Namora,no\n"
            "SALUD,Centro de Salud Jesús,,-7.2459,-78.3791,Jesús,\n"
            "COMISARIA,Comisaría Jesús,957-686-482,-7.2459,-78.3791,Jesús,quizás\n"
        )

        resultado = self.importar(csv).json()

        self.assertEqual(resultado["creados"], 3)
        self.assertEqual(resultado["con_ubicacion_aproximada"], 1)
        self.assertIn("ubicacion_aproximada", resultado["rechazados"][0]["motivo"])
        puntos = {punto["nombre"]: punto for punto in self.directorio()["puntos"]}
        self.assertTrue(puntos["Comisaría Namora"]["ubicacion_aproximada"])
        self.assertFalse(puntos["Centro de Salud Namora"]["ubicacion_aproximada"])
        self.assertFalse(puntos["Centro de Salud Jesús"]["ubicacion_aproximada"])
        # Al volver a cargarla con coordenadas exactas deja de ser aproximada.
        exacta = csv.splitlines()[0] + "\nCOMISARIA,Comisaría Namora,957-686-775,-7.2021,-78.3250,Namora,no\n"
        self.importar(exacta)
        self.assertFalse({p["nombre"]: p for p in self.directorio()["puntos"]}["Comisaría Namora"]["ubicacion_aproximada"])

    def test_las_filas_invalidas_se_informan_y_no_se_guardan(self):
        csv = (
            "tipo,nombre,telefono,latitud,longitud,distrito\n"
            "COMISARIA,Comisaría Válida,076 111111,-7.1,-78.5,Cajamarca\n"
            "COMISARIA,X,076 111111,-7.1,-78.5,Cajamarca\n"
            "COMISARIA,Sin coordenadas,076 111111,,,Cajamarca\n"
            "COMISARIA,Fuera de rango,076 111111,-97.1,-78.5,Cajamarca\n"
            "COMISARIA,Teléfono raro,llamar a Juan,-7.1,-78.5,Cajamarca\n"
            "TALLER,Tipo desconocido,076 111111,-7.1,-78.5,Cajamarca\n"
            "COMISARIA,Comisaría Válida,076 222222,-7.2,-78.6,Cajamarca\n"
            "COMISARIA,Punto cero,076 111111,0,0,Cajamarca\n"
        )

        resultado = self.importar(csv).json()

        self.assertEqual(resultado["creados"], 1)
        self.assertEqual(resultado["total_rechazados"], 7)
        self.assertEqual([fila["fila"] for fila in resultado["rechazados"]], [3, 4, 5, 6, 7, 8, 9])
        self.assertIn("teléfono inválido", resultado["rechazados"][3]["motivo"])
        self.assertEqual(self.directorio()["total"], 1)

    def test_un_archivo_sin_las_columnas_necesarias_se_rechaza_explicando_cuales_faltan(self):
        sin_coordenadas = self.importar("nombre,telefono\nComisaría Cajamarca,076 362165\n")
        self.assertEqual(sin_coordenadas.status_code, 400)
        self.assertIn("latitud", self.mensaje(sin_coordenadas))
        self.assertIn("tipo", self.mensaje(sin_coordenadas))
        self.assertEqual(self.directorio()["total"], 0)

    def test_reimportar_actualiza_en_lugar_de_duplicar(self):
        owner = self.token_propietario()
        self.importar(CSV_COMAS, owner)
        corregido = CSV_COMAS.replace("(076) 362165", "076 999000")

        segunda = self.importar(corregido, owner).json()

        self.assertEqual((segunda["creados"], segunda["actualizados"]), (0, 3))
        puntos = {punto["nombre"]: punto for punto in self.directorio()["puntos"]}
        self.assertEqual(len(puntos), 3)
        self.assertEqual(puntos["Comisaría Cajamarca"]["telefono"], "076 999000")

    def test_la_version_evita_volver_a_descargar_y_cambia_con_cada_correccion(self):
        owner = self.token_propietario()
        self.importar(CSV_COMAS, owner)
        version = self.directorio()["version"]

        igual = self.directorio(version=version)
        self.assertTrue(igual["sin_cambios"])
        self.assertEqual(igual["puntos"], [])
        self.assertEqual(igual["total"], 3)

        punto = self.client.get(f"{API}/admin/directory", headers=self.auth(owner), params={"q": "bomberos"}).json()[0]
        baja = self.client.patch(f"{API}/admin/directory/{punto['id']}", headers=self.auth(owner), json={"activo": False})
        self.assertEqual(baja.status_code, 200)

        despues = self.directorio(version=version)
        self.assertFalse(despues["sin_cambios"])
        self.assertNotEqual(despues["version"], version)
        self.assertEqual(despues["total"], 2)
        self.assertNotIn("BOMBEROS", {p["tipo"] for p in despues["puntos"]})

    def test_cambiar_un_telefono_exige_fuente_y_fecha_de_verificacion(self):
        owner = self.token_propietario()
        self.importar(CSV_COMAS, owner)
        punto = self.client.get(f"{API}/admin/directory", headers=self.auth(owner), params={"q": "Comisaría"}).json()[0]
        url = f"{API}/admin/directory/{punto['id']}"

        sin_fuente = self.client.patch(url, headers=self.auth(owner), json={"telefono": "076 555000"})
        self.assertEqual(sin_fuente.status_code, 400)
        invalido = self.client.patch(url, headers=self.auth(owner), json={"telefono": "no sé", "fuente": FUENTE, "verificado_en": HOY})
        self.assertEqual(invalido.status_code, 422)
        futura = self.client.patch(url, headers=self.auth(owner), json={
            "telefono": "076 555000", "fuente": FUENTE, "verificado_en": (date.today() + timedelta(days=2)).isoformat(),
        })
        self.assertEqual(futura.status_code, 400)

        corregido = self.client.patch(url, headers=self.auth(owner), json={
            "telefono": "076 555000", "fuente": "Llamada de comprobación al número publicado", "verificado_en": HOY,
        })
        self.assertEqual(corregido.status_code, 200, corregido.text)
        self.assertEqual(corregido.json()["telefono"], "076 555000")
        self.assertEqual(corregido.json()["fuente"], "Llamada de comprobación al número publicado")

    def test_alta_manual_valida_los_datos_y_no_permite_duplicados(self):
        owner = self.token_propietario()
        nuevo = {
            "tipo": "SERENAZGO", "nombre": "Serenazgo Cajamarca", "telefono": "076 599000",
            "latitud": -7.1565, "longitud": -78.5170, "distrito": "Cajamarca",
            "fuente": "Página oficial de la municipalidad", "verificado_en": HOY,
        }

        alta = self.client.post(f"{API}/admin/directory", headers=self.auth(owner), json=nuevo)
        self.assertEqual(alta.status_code, 201, alta.text)
        duplicado = self.client.post(f"{API}/admin/directory", headers=self.auth(owner), json=nuevo)
        self.assertEqual(duplicado.status_code, 400)
        for cambio in ({"tipo": "TALLER"}, {"latitud": 120}, {"fuente": "corta"}, {"telefono": "abc"}):
            invalido = self.client.post(f"{API}/admin/directory", headers=self.auth(owner), json={**nuevo, "nombre": "Otro", **cambio})
            self.assertEqual(invalido.status_code, 422, cambio)

        resumen = self.client.get(f"{API}/admin/directory/summary", headers=self.auth(owner)).json()
        self.assertEqual(resumen["total_activos"], 1)
        self.assertEqual(resumen["por_tipo"], {"SERENAZGO": 1})
        self.assertEqual(resumen["verificacion_mas_antigua"], HOY)

    def test_solo_el_propietario_modifica_el_directorio(self):
        ciudadano = self.token_ciudadano()
        director = self.token_director_aprobado()
        for token in (ciudadano, director):
            self.assertEqual(self.importar(CSV_COMAS, token).status_code, 403)
            self.assertEqual(self.client.get(f"{API}/admin/directory", headers=self.auth(token)).status_code, 403)
            self.assertEqual(self.client.patch(f"{API}/admin/directory/1", headers=self.auth(token), json={"activo": False}).status_code, 403)
        self.assertEqual(self.client.post(f"{API}/admin/directory/import", json={"csv": CSV_COMAS, "fuente": FUENTE, "verificado_en": HOY}).status_code, 401)
        self.assertEqual(self.directorio()["total"], 0)
