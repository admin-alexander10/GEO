"""Arma los CSV del directorio de emergencia para el departamento de Cajamarca.

Fuentes (se descargan a mano; el script no accede a internet):

  1. Prontuario telefónico de las comisarías del Frente Policial Cajamarca (PNP, PDF).
     Aporta nombre, dirección y teléfono. No trae coordenadas.
  2. Relación de comisarías básicas en operaciones a nivel nacional (PNP, PDF).
     Aporta provincia y distrito de cada comisaría. No trae coordenadas.
  3. RENIPRESS / IPRESS.csv (SUSALUD, Datos Abiertos).
     Aporta los establecimientos de salud con coordenadas y teléfono.

Como ninguna fuente policial trae coordenadas, cada comisaría se ubica con las
coordenadas del establecimiento de salud público del MISMO poblado (mismo
distrito y mismo nombre). Es una aproximación a nivel de poblado, por eso todas
las comisarías salen con `ubicacion_aproximada = si`. Las que no tienen un
poblado identificable quedan fuera y se listan en el informe para completarlas.

Uso (requiere `pdftotext`, del paquete poppler):

    python scripts/armar_directorio_cajamarca.py PRONTUARIO.pdf RELACION.pdf IPRESS.csv CARPETA_DE_SALIDA
"""
from __future__ import annotations

import collections
import csv
import io
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

DEPARTAMENTO = "CAJAMARCA"
PREFIJO_FIJO = "076"  # código de área de todo el departamento
# Límites generosos del departamento, para descartar coordenadas imposibles.
LATITUD = (-8.0, -4.5)
LONGITUD = (-79.7, -77.6)
INSTITUCIONES_PUBLICAS = {"GOBIERNO REGIONAL", "MINSA", "ESSALUD"}
# Centros de salud con médico y hospitales. Los puestos de salud (I-1, I-2) quedan fuera.
CATEGORIAS_SALUD = {"I-3", "I-4", "II-1", "II-2", "II-E", "III-1", "III-2", "III-E"}
PESO_CATEGORIA = {"III-2": 9, "III-1": 8, "III-E": 8, "II-2": 7, "II-E": 6, "II-1": 6, "I-4": 5, "I-3": 4, "I-2": 3, "I-1": 2}

# Comisarías cuyo nombre en el prontuario no coincide con el de la relación nacional.
# Valor: nombre en la relación, o (provincia, distrito, poblado) cuando no figura en ella.
EQUIVALENCIAS = {
    "EDUARDO VILLANUEVA LA GRAMA": "LA GRAMA",
    "CATILUC": "CATILLUC",
    "SANTA CRUZ TOLEDO": "SANTA CRUZ DE TOLEDO",
    "EL SALITRE": "SALITRE",
    "HUALGAYOC BAMBAMARCA": "BAMBAMARCA",
    "ALGAMARCA": ("CAJABAMBA", "CACHACHI", "ALGAMARCA"),
    # La Comisaría de Familia no es "básica" y no figura en la relación nacional.
    "FAMILIA CAJAMARCA": ("CAJAMARCA", "CAJAMARCA", "FAMILIA CAJAMARCA"),
}
# Ciudades con varias comisarías: el nombre no identifica un poblado, así que no se
# les puede asignar una ubicación sin inventarla. Quedan pendientes de coordenadas.
SIN_POBLADO_PROPIO = {"FAMILIA CAJAMARCA", "SAN JOSE"}
# La Comisaría Central (Jr. Amalia Puga 1111, centro de la ciudad) se ubica con el
# establecimiento público de mayor categoría del centro, a unas cuadras. Es la única
# de la ciudad que se carga, para que quien esté en Cajamarca no vea como más cercana
# la de otro distrito. Sigue marcada como aproximada.
REFERENCIA_EN_CIUDAD = {"CENTRAL CAJAMARCA": "SIMON BOLIVAR"}
MINUSCULAS = {"De", "Del", "La", "Las", "Los", "El", "Y", "E"}


def clave(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto or "")
    plano = "".join(c for c in plano if not unicodedata.combining(c)).upper()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", plano).split())


def titulo(texto: str) -> str:
    palabras = " ".join(texto.split()).title().split(" ")
    arreglo = []
    for i, palabra in enumerate(palabras):
        if re.fullmatch(r"(Ii|Iii|Iv|Vi|Vii)", palabra):
            palabra = palabra.upper()  # números romanos: "Hospital II"
        elif i and palabra in MINUSCULAS:
            palabra = palabra.lower()
        arreglo.append(palabra)
    return " ".join(arreglo)


def texto_pdf(ruta: str) -> str:
    return subprocess.run(["pdftotext", "-layout", ruta, "-"], check=True, capture_output=True).stdout.decode("utf-8")


# --------------------------------------------------------------------------
# Fuentes policiales
# --------------------------------------------------------------------------
def leer_prontuario(texto: str) -> list[dict]:
    entradas, actual, campo = [], None, None
    for linea in texto.splitlines():
        m = re.match(r"\s*(Comisaría PNP|Dirección|Teléfono)\s*:\s*(.*)$", linea)
        if m:
            etiqueta, valor = m.group(1), m.group(2).strip()
            if etiqueta == "Comisaría PNP":
                actual = {"nombre": valor, "direccion": "", "telefono_texto": ""}
                entradas.append(actual)
                campo = "nombre"
            elif actual is not None and etiqueta == "Dirección":
                actual["direccion"], campo = valor, "direccion"
            elif actual is not None:
                actual["telefono_texto"], campo = valor, "telefono_texto"
        elif linea.strip() and actual is not None and campo in ("nombre", "direccion"):
            actual[campo] = f"{actual[campo]} {linea.strip()}".strip()
    return entradas


def nucleo(nombre: str) -> str:
    """'Comisaría PNP Rural Sectorial Baños del Inca “B”' -> 'BANOS DEL INCA'."""
    sin_categoria = re.sub(r"[“”\"']\s*[A-E]\s*[“”\"']", " ", nombre)
    limpio = re.sub(r"^(COMISARIA PNP|CPNP)\s+", "", clave(sin_categoria))
    return " ".join(re.sub(r"\b(RURAL|SECTORIAL)\b", " ", limpio).split())


def leer_relacion(texto: str) -> dict[str, dict]:
    patron = re.compile(
        r"^\s*\d+\s+.+?\s{2,}\d{3,4}\s+\d{5,6}\s+(CPNP .+?)\s{2,}[A-E]\s+\d+\s+(.+?)\s{2,}(.+?)\s{2,}(.+?)\s*$"
    )
    relacion = {}
    for linea in texto.splitlines():
        m = patron.match(linea)
        if m and clave(m.group(2)) == DEPARTAMENTO:
            relacion[nucleo(m.group(1))] = {
                "provincia": clave(m.group(3)), "distrito": clave(m.group(4)), "distrito_texto": m.group(4).strip(),
            }
    return relacion


def telefono_comisaria(texto: str) -> str:
    """Solo se acepta un número propio; 'S/N CEOPOL ...' significa que la comisaría no tiene."""
    m = re.fullmatch(r"(\d{3})-(\d{3})-(\d{3})", texto.strip())
    return "".join(m.groups()) if m else ""


# --------------------------------------------------------------------------
# RENIPRESS
# --------------------------------------------------------------------------
def leer_ipress(ruta: str) -> list[dict]:
    crudo = Path(ruta).read_bytes()
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    filas = []
    for fila in csv.DictReader(io.StringIO(texto)):
        if clave(fila["Departamento"]) != DEPARTAMENTO or fila["Condición"].strip() != "EN FUNCIONAMIENTO":
            continue
        try:
            a, b = float(fila["NORTE"]), float(fila["ESTE"])
        except ValueError:
            continue
        # En el archivo publicado la columna NORTE trae la longitud y ESTE la latitud.
        longitud, latitud = (a, b) if a < -60 else (b, a)
        if not (LATITUD[0] <= latitud <= LATITUD[1] and LONGITUD[0] <= longitud <= LONGITUD[1]):
            continue
        fila["_lat"], fila["_lng"] = round(latitud, 6), round(longitud, 6)
        fila["_prov"], fila["_dist"], fila["_nombre"] = clave(fila["Provincia"]), clave(fila["Distrito"]), clave(fila["Nombre del establecimiento"])
        filas.append(fila)
    return filas


def telefono_salud(texto: str) -> str:
    """Primer número utilizable del campo; '' si solo hay 'NO CUENTA', 'RADIO', códigos RPM, etc."""
    for parte in re.split(r"[/,;]| - | y ", texto or ""):
        digitos = re.sub(r"\D", "", parte)
        if re.fullmatch(r"9\d{8}", digitos):
            return digitos
        if re.fullmatch(rf"{PREFIJO_FIJO}\d{{6}}", digitos):
            return f"{PREFIJO_FIJO} {digitos[3:]}"
        if re.fullmatch(r"[2-8]\d{5}", digitos):  # fijo local sin código de área
            return f"{PREFIJO_FIJO} {digitos}"
    return ""


def nombre_salud(fila: dict) -> str:
    nombre = titulo(fila["Nombre del establecimiento"])
    base = clave(nombre)
    clasificacion = clave(fila["Clasificación"])
    if fila["Institución"] == "ESSALUD" and "ESSALUD" not in base:
        nombre = f"{nombre} (EsSalud)"
    if any(palabra in base for palabra in ("HOSPITAL", "CENTRO", "POLICLINICO", "POSTA", "CAP ", "CLINICA")):
        return nombre
    prefijo = "Hospital" if "HOSPITAL" in clasificacion else "Centro de Salud"
    return titulo(f"{prefijo} {nombre}")


def mismo_distrito(a: str, b: str) -> bool:
    # RENIPRESS recorta los nombres largos ("SANTA CRUZ DE TOLED").
    return a == b or (len(a) >= 15 and b.startswith(a)) or (len(b) >= 15 and a.startswith(b))


def ancla(poblado: str, provincia: str, distrito: str, ipress: list[dict]):
    """Establecimiento público del mismo distrito cuyo nombre es el del poblado."""
    candidatos = [
        f for f in ipress
        if f["Institución"] in INSTITUCIONES_PUBLICAS and f["_prov"] == provincia and mismo_distrito(f["_dist"], distrito)
    ]
    sin_articulo = re.sub(r"^(LA|EL|LOS|LAS) ", "", poblado)

    def coincide(nombre: str) -> bool:
        return (
            nombre in (poblado, sin_articulo)
            or sorted(nombre.split()) == sorted(poblado.split())  # "CATAN TANTARICA" = "TANTARICA CATAN"
            or sin_articulo in nombre.split()
            or (len(sin_articulo) > 5 and sin_articulo in nombre)
            or (len(nombre) > 5 and nombre in poblado)
        )

    coincidencias = [f for f in candidatos if coincide(f["_nombre"])]
    if not coincidencias:
        return None
    return max(coincidencias, key=lambda f: PESO_CATEGORIA.get(f["Categoria"].strip(), 0))


# --------------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__)
        return 2
    prontuario = leer_prontuario(texto_pdf(sys.argv[1]))
    relacion = leer_relacion(texto_pdf(sys.argv[2]))
    ipress = leer_ipress(sys.argv[3])
    salida = Path(sys.argv[4])
    salida.mkdir(parents=True, exist_ok=True)
    columnas = ["tipo", "nombre", "telefono", "latitud", "longitud", "direccion", "distrito", "ubicacion_aproximada"]
    informe: list[str] = []

    # ---------------- comisarías
    comisarias, pendientes = [], []
    for entrada in prontuario:
        nombre = " ".join(entrada["nombre"].replace("“", '"').replace("”", '"').split())
        clave_nombre = nucleo(entrada["nombre"])
        equivalencia = EQUIVALENCIAS.get(clave_nombre, clave_nombre)
        if isinstance(equivalencia, tuple):
            provincia, distrito, poblado = equivalencia
            distrito_texto = distrito
        elif equivalencia in relacion:
            provincia, distrito, poblado = relacion[equivalencia]["provincia"], relacion[equivalencia]["distrito"], equivalencia
            distrito_texto = relacion[equivalencia]["distrito_texto"]
        else:
            # No figura en la relación de comisarías básicas (p. ej. la Comisaría de Familia).
            provincia = distrito = poblado = distrito_texto = ""
        referencia = None
        if clave_nombre in REFERENCIA_EN_CIUDAD:
            referencia = ancla(REFERENCIA_EN_CIUDAD[clave_nombre], provincia, distrito, ipress)
        elif clave_nombre not in SIN_POBLADO_PROPIO and poblado:
            referencia = ancla(poblado, provincia, distrito, ipress)
        if referencia is None:
            motivo = (
                "ciudad con varias comisarías: hace falta la coordenada exacta del local"
                if clave_nombre in SIN_POBLADO_PROPIO or not poblado
                else "no hay un establecimiento de salud con el nombre de ese poblado para ubicarla"
            )
            pendientes.append({
                "tipo": "COMISARIA", "nombre": nombre, "telefono": telefono_comisaria(entrada["telefono_texto"]),
                "latitud": "", "longitud": "", "direccion": entrada["direccion"], "distrito": titulo(distrito_texto),
                "ubicacion_aproximada": "no", "motivo_pendiente": motivo,
            })
            continue
        comisarias.append({
            "tipo": "COMISARIA", "nombre": nombre, "telefono": telefono_comisaria(entrada["telefono_texto"]),
            "latitud": referencia["_lat"], "longitud": referencia["_lng"], "direccion": entrada["direccion"],
            "distrito": titulo(distrito_texto), "ubicacion_aproximada": "si",
            "_referencia": titulo(referencia["Nombre del establecimiento"]),
        })

    # ---------------- salud
    salud, vistos = [], set()
    for fila in ipress:
        if (
            fila["Institución"] not in INSTITUCIONES_PUBLICAS
            or not fila["Tipo"].startswith("ESTABLECIMIENTO DE SALUD")
            or fila["Categoria"].strip() not in CATEGORIAS_SALUD
        ):
            continue
        nombre = nombre_salud(fila)
        distrito = titulo(fila["Distrito"])
        identidad = (clave(nombre), clave(distrito))
        if identidad in vistos:
            nombre = f"{nombre} ({fila['Categoria'].strip()}, código {fila['Código Único'].strip()})"
            identidad = (clave(nombre), clave(distrito))
        vistos.add(identidad)
        salud.append({
            "tipo": "SALUD", "nombre": nombre, "telefono": telefono_salud(fila["Teléfono"]),
            "latitud": fila["_lat"], "longitud": fila["_lng"], "direccion": titulo(fila["Dirección"])[:300],
            "distrito": distrito, "ubicacion_aproximada": "no",
        })

    def escribir(nombre_archivo: str, filas: list[dict], extra: list[str] = ()) -> None:
        with open(salida / nombre_archivo, "w", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=columnas + list(extra), extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(filas)

    escribir("directorio_cajamarca_comisarias.csv", comisarias)
    escribir("directorio_cajamarca_salud.csv", salud)
    escribir("comisarias_pendientes_de_coordenadas.csv", pendientes, ["motivo_pendiente"])

    repetidos = [t for t, n in collections.Counter(c["telefono"] for c in comisarias + pendientes if c["telefono"]).items() if n > 1]
    informe.append(f"Comisarías en el prontuario: {len(prontuario)}")
    informe.append(f"  ubicadas (aproximación por poblado): {len(comisarias)}")
    informe.append(f"    con teléfono propio: {sum(1 for c in comisarias if c['telefono'])}")
    informe.append(f"    sin teléfono propio (el prontuario remite al CEOPOL): {sum(1 for c in comisarias if not c['telefono'])}")
    informe.append(f"  pendientes de coordenadas: {len(pendientes)}")
    for p in pendientes:
        informe.append(f"    - {p['nombre']} | {p['direccion']} | {p['motivo_pendiente']}")
    informe.append("Teléfonos que el prontuario repite en más de una comisaría (revisar):")
    for telefono in repetidos:
        nombres = [c["nombre"] for c in comisarias + pendientes if c["telefono"] == telefono]
        informe.append(f"    - {telefono}: {'; '.join(nombres)}")
    informe.append(f"Establecimientos de salud públicos I-3 o superior: {len(salud)}")
    informe.append(f"    con teléfono utilizable: {sum(1 for s in salud if s['telefono'])}")
    informe.append(f"    sin teléfono: {sum(1 for s in salud if not s['telefono'])}")
    informe.append("Referencia usada para ubicar cada comisaría:")
    for c in comisarias:
        informe.append(f"    - {c['nombre']} -> {c['_referencia']} ({c['distrito']})")
    (salida / "INFORME.txt").write_text("\n".join(informe) + "\n", encoding="utf-8")
    print("\n".join(informe[: 12 + len(pendientes) + len(repetidos)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
