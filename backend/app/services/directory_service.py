import csv
import io
import unicodedata
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.exceptions import DomainException, EntityNotFoundException
from app.models.directory import PuntoEmergencia
from app.schemas.directory import (
    TIPOS_PUNTO,
    DirectorioPublico,
    FilaRechazada,
    ImportacionRequest,
    ImportacionResponse,
    PuntoActualizar,
    PuntoCrear,
    ResumenDirectorio,
    normalizar_telefono,
)

MAX_FILAS = 20_000
MAX_RECHAZOS_DETALLADOS = 50

# Nombres de columna aceptados en el CSV (sin tildes, en minúsculas).
ALIAS_COLUMNAS = {
    "tipo": {"tipo", "tipo_punto", "categoria"},
    "nombre": {"nombre", "nombre_comisaria", "comisaria", "establecimiento", "nombre_establecimiento", "compania", "nombre_compania"},
    "telefono": {"telefono", "telefonos", "telefono_fijo", "celular", "fono"},
    "latitud": {"latitud", "lat", "y", "coord_y", "coordenada_y"},
    "longitud": {"longitud", "lng", "lon", "long", "x", "coord_x", "coordenada_x"},
    "direccion": {"direccion", "domicilio"},
    "distrito": {"distrito", "nombdist", "nombre_distrito"},
    "ubicacion_aproximada": {"ubicacion_aproximada", "aproximada", "coordenadas_aproximadas"},
}
VALORES_SI = {"1", "si", "s", "true", "verdadero", "x", "aprox", "aproximada"}
VALORES_NO = {"", "0", "no", "n", "false", "falso", "exacta"}
ALIAS_TIPOS = {
    "COMISARIA": {"comisaria", "comisarias", "pnp", "policia"},
    "BOMBEROS": {"bomberos", "bombero", "compania de bomberos", "cgbvp"},
    "SALUD": {"salud", "hospital", "centro de salud", "posta", "puesto de salud", "clinica", "samu"},
    "SERENAZGO": {"serenazgo", "seguridad ciudadana"},
    "OTRO": {"otro", "otros"},
}


def _sin_tildes(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto)
    return "".join(caracter for caracter in plano if not unicodedata.combining(caracter))


def _clave(texto: Optional[str]) -> str:
    return " ".join(_sin_tildes(texto or "").lower().split())


class DirectoryService:
    """Directorio público de puntos de atención locales."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Lectura pública
    # ------------------------------------------------------------------
    def version(self) -> str:
        """Cambia cada vez que se crea, corrige o desactiva una entrada."""
        total, ultimo = self.db.query(
            func.count(PuntoEmergencia.id),
            func.max(PuntoEmergencia.actualizado_en),
        ).one()
        return f"{total}-{ultimo.isoformat() if ultimo else 'vacio'}"

    def directorio_publico(self, version_cliente: Optional[str] = None) -> DirectorioPublico:
        version = self.version()
        total = self.db.query(PuntoEmergencia).filter(PuntoEmergencia.activo.is_(True)).count()
        if version_cliente and version_cliente == version:
            return DirectorioPublico(version=version, sin_cambios=True, total=total)
        puntos = self.db.query(PuntoEmergencia).filter(
            PuntoEmergencia.activo.is_(True),
        ).order_by(PuntoEmergencia.id).all()
        return DirectorioPublico(version=version, total=total, puntos=puntos)

    # ------------------------------------------------------------------
    # Administración (propietario)
    # ------------------------------------------------------------------
    def resumen(self) -> ResumenDirectorio:
        activos = self.db.query(PuntoEmergencia).filter(PuntoEmergencia.activo.is_(True))
        por_tipo = {
            tipo: cantidad
            for tipo, cantidad in self.db.query(PuntoEmergencia.tipo, func.count(PuntoEmergencia.id))
            .filter(PuntoEmergencia.activo.is_(True))
            .group_by(PuntoEmergencia.tipo)
            .all()
        }
        return ResumenDirectorio(
            total_activos=activos.count(),
            por_tipo=por_tipo,
            sin_telefono=activos.filter(PuntoEmergencia.telefono.is_(None)).count(),
            verificacion_mas_antigua=self.db.query(func.min(PuntoEmergencia.verificado_en))
            .filter(PuntoEmergencia.activo.is_(True))
            .scalar(),
        )

    def buscar(self, texto: str = "", tipo: Optional[str] = None, limit: int = 30) -> List[PuntoEmergencia]:
        consulta = self.db.query(PuntoEmergencia)
        if tipo:
            consulta = consulta.filter(PuntoEmergencia.tipo == tipo)
        termino = _clave(texto)
        if termino:
            patron = f"%{termino}%"
            consulta = consulta.filter(
                PuntoEmergencia.nombre_clave.like(patron) | PuntoEmergencia.distrito_clave.like(patron)
            )
        return consulta.order_by(PuntoEmergencia.activo.desc(), PuntoEmergencia.nombre).limit(max(1, min(limit, 100))).all()

    def _existente(self, tipo: str, nombre: str, distrito: Optional[str]) -> Optional[PuntoEmergencia]:
        return self.db.query(PuntoEmergencia).filter(
            PuntoEmergencia.tipo == tipo,
            PuntoEmergencia.nombre_clave == _clave(nombre)[:200],
            PuntoEmergencia.distrito_clave == _clave(distrito)[:120],
        ).first()

    def crear(self, datos: PuntoCrear) -> PuntoEmergencia:
        if self._existente(datos.tipo, datos.nombre, datos.distrito):
            raise DomainException("Ya existe una entrada con ese tipo, nombre y distrito. Corrígela en lugar de duplicarla.", "DIRECTORY_DUPLICATE")
        ahora = datetime.utcnow()
        punto = PuntoEmergencia(
            **datos.model_dump(),
            nombre_clave=_clave(datos.nombre)[:200],
            distrito_clave=_clave(datos.distrito)[:120],
            activo=True,
            creado_en=ahora,
            actualizado_en=ahora,
        )
        self.db.add(punto)
        self.db.commit()
        self.db.refresh(punto)
        return punto

    def actualizar(self, punto_id: int, cambios: PuntoActualizar) -> PuntoEmergencia:
        punto = self.db.query(PuntoEmergencia).filter(PuntoEmergencia.id == punto_id).first()
        if not punto:
            raise EntityNotFoundException("Entrada del directorio", str(punto_id))
        enviados = cambios.model_fields_set
        if "telefono" in enviados and cambios.telefono != punto.telefono:
            if not cambios.fuente or not cambios.verificado_en:
                raise DomainException("Para cambiar un teléfono indica la fuente y la fecha en que lo verificaste.", "DIRECTORY_SOURCE_REQUIRED")
            if cambios.verificado_en > date.today():
                raise DomainException("La fecha de verificación no puede ser futura.", "DIRECTORY_FUTURE_DATE")
            punto.telefono = cambios.telefono
            punto.fuente = " ".join(cambios.fuente.split())
            punto.verificado_en = cambios.verificado_en
        if cambios.activo is not None:
            punto.activo = cambios.activo
        punto.actualizado_en = datetime.utcnow()
        self.db.add(punto)
        self.db.commit()
        self.db.refresh(punto)
        return punto

    # ------------------------------------------------------------------
    # Importación desde CSV
    # ------------------------------------------------------------------
    @staticmethod
    def _leer_csv(texto: str) -> Tuple[List[str], List[Dict[str, str]], str]:
        contenido = texto.lstrip("﻿")
        primera = contenido.splitlines()[0] if contenido.strip() else ""
        # Excel en español exporta con punto y coma (y usa coma como separador decimal).
        delimitador = ";" if primera.count(";") > primera.count(",") else ","
        lector = csv.DictReader(io.StringIO(contenido), delimiter=delimitador)
        encabezados = [campo for campo in (lector.fieldnames or []) if campo is not None]
        return encabezados, list(lector), delimitador

    @staticmethod
    def _mapear_columnas(encabezados: List[str]) -> Dict[str, str]:
        mapa: Dict[str, str] = {}
        for original in encabezados:
            clave = _clave(original).replace(" ", "_")
            for campo, alias in ALIAS_COLUMNAS.items():
                if campo not in mapa and clave in alias:
                    mapa[campo] = original
        return mapa

    @staticmethod
    def _tipo_desde_texto(valor: str) -> Optional[str]:
        clave = _clave(valor)
        if clave.upper() in TIPOS_PUNTO:
            return clave.upper()
        return next((tipo for tipo, alias in ALIAS_TIPOS.items() if clave in alias), None)

    @staticmethod
    def _numero(valor: str, delimitador: str) -> float:
        texto = (valor or "").strip()
        if delimitador == ";":
            texto = texto.replace(",", ".")
        return float(texto)

    def importar(self, solicitud: ImportacionRequest) -> ImportacionResponse:
        encabezados, filas, delimitador = self._leer_csv(solicitud.csv)
        columnas = self._mapear_columnas(encabezados)
        obligatorias = [campo for campo in ("nombre", "latitud", "longitud") if campo not in columnas]
        if "tipo" not in columnas and not solicitud.tipo_por_defecto:
            obligatorias.append("tipo (o elige un tipo para todo el archivo)")
        if obligatorias:
            raise DomainException(
                f"Al archivo le faltan columnas: {', '.join(obligatorias)}. "
                f"Columnas encontradas: {', '.join(encabezados) or 'ninguna'}.",
                "DIRECTORY_CSV_COLUMNS",
            )
        if len(filas) > MAX_FILAS:
            raise DomainException(f"El archivo tiene más de {MAX_FILAS} filas; divídelo en partes.", "DIRECTORY_CSV_TOO_LARGE")

        fuente = " ".join(solicitud.fuente.split())
        ahora = datetime.utcnow()
        creados = actualizados = sin_telefono = aproximadas = 0
        rechazados: List[FilaRechazada] = []
        vistos = set()

        def rechazar(numero: int, motivo: str) -> None:
            rechazados.append(FilaRechazada(fila=numero, motivo=motivo))

        def celda(fila: Dict[str, str], campo: str) -> str:
            return (fila.get(columnas[campo]) or "").strip() if campo in columnas else ""

        for numero, fila in enumerate(filas, start=2):  # la fila 1 es el encabezado
            nombre = " ".join(celda(fila, "nombre").split())
            if len(nombre) < 3:
                rechazar(numero, "nombre vacío o demasiado corto")
                continue
            tipo = self._tipo_desde_texto(celda(fila, "tipo")) if "tipo" in columnas else solicitud.tipo_por_defecto
            if "tipo" in columnas and not tipo:
                tipo = solicitud.tipo_por_defecto if not celda(fila, "tipo") else None
            if not tipo:
                rechazar(numero, f"tipo no reconocido: «{celda(fila, 'tipo')[:40]}»")
                continue
            try:
                latitud = self._numero(celda(fila, "latitud"), delimitador)
                longitud = self._numero(celda(fila, "longitud"), delimitador)
            except ValueError:
                rechazar(numero, "latitud o longitud no numéricas")
                continue
            if not (-90 <= latitud <= 90 and -180 <= longitud <= 180) or (latitud == 0 and longitud == 0):
                rechazar(numero, "coordenadas fuera de rango")
                continue
            try:
                telefono = normalizar_telefono(celda(fila, "telefono"))
            except ValueError:
                rechazar(numero, f"teléfono inválido: «{celda(fila, 'telefono')[:40]}»")
                continue
            aproximada_texto = _clave(celda(fila, "ubicacion_aproximada"))
            if aproximada_texto not in VALORES_SI and aproximada_texto not in VALORES_NO:
                rechazar(numero, f"ubicacion_aproximada debe ser sí o no: «{celda(fila, 'ubicacion_aproximada')[:20]}»")
                continue
            aproximada = aproximada_texto in VALORES_SI
            distrito = " ".join(celda(fila, "distrito").split())[:120] or None
            direccion = " ".join(celda(fila, "direccion").split())[:300] or None
            identidad = (tipo, _clave(nombre)[:200], _clave(distrito)[:120])
            if identidad in vistos:
                rechazar(numero, "repetida dentro del mismo archivo (mismo tipo, nombre y distrito)")
                continue
            vistos.add(identidad)

            existente = self._existente(tipo, nombre[:200], distrito)
            if existente:
                existente.telefono = telefono
                existente.direccion = direccion
                existente.latitud = latitud
                existente.longitud = longitud
                existente.ubicacion_aproximada = aproximada
                existente.fuente = fuente
                existente.verificado_en = solicitud.verificado_en
                existente.activo = True
                existente.actualizado_en = ahora
                self.db.add(existente)
                actualizados += 1
            else:
                self.db.add(PuntoEmergencia(
                    tipo=tipo, nombre=nombre[:200], telefono=telefono, direccion=direccion, distrito=distrito,
                    nombre_clave=_clave(nombre)[:200], distrito_clave=_clave(distrito)[:120],
                    latitud=latitud, longitud=longitud, ubicacion_aproximada=aproximada,
                    fuente=fuente, verificado_en=solicitud.verificado_en,
                    activo=True, creado_en=ahora, actualizado_en=ahora,
                ))
                creados += 1
            if telefono is None:
                sin_telefono += 1
            if aproximada:
                aproximadas += 1

        self.db.commit()
        return ImportacionResponse(
            creados=creados,
            actualizados=actualizados,
            sin_telefono=sin_telefono,
            con_ubicacion_aproximada=aproximadas,
            rechazados=rechazados[:MAX_RECHAZOS_DETALLADOS],
            total_rechazados=len(rechazados),
            columnas_detectadas=[f"{campo} <- {original}" for campo, original in columnas.items()],
        )
