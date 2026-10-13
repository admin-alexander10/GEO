"""Sincronización del esquema de PostgreSQL con lo que el backend espera.

`Base.metadata.create_all` crea tablas nuevas pero no agrega columnas a las
que ya existen. Cuando el código avanza y la base local no, aparecen errores
500 difíciles de leer (por ejemplo "Error al cargar familiares"). Este módulo
detecta esa diferencia y aplica las migraciones aditivas de
`database/migrations/`, que se pueden repetir sin riesgo.

Lo usan `scripts/preparar_bd.py` y el arranque del backend (`main.py`).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.db.base import Base

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[3]
DIRECTORIO_MIGRACIONES = RAIZ_REPOSITORIO / "database" / "migrations"
ESQUEMA_INICIAL = RAIZ_REPOSITORIO / "database" / "init_db.sql"

ResultadoArchivo = Tuple[str, bool, str]


def columnas_faltantes(engine: Engine) -> Dict[str, List[str]]:
    """Devuelve {tabla: [columnas que el backend usa y la base no tiene]}."""
    import app.models  # noqa: F401  (registra todos los modelos en Base.metadata)

    inspector = inspect(engine)
    existentes = set(inspector.get_table_names())
    faltantes: Dict[str, List[str]] = {}
    for nombre, tabla in Base.metadata.tables.items():
        if nombre not in existentes:
            faltantes[nombre] = ["(la tabla no existe)"]
            continue
        columnas = {columna["name"] for columna in inspector.get_columns(nombre)}
        ausentes = [columna.name for columna in tabla.columns if columna.name not in columnas]
        if ausentes:
            faltantes[nombre] = ausentes
    return faltantes


def archivos_de_migracion() -> List[Path]:
    """Migraciones hacia adelante, en orden. Las reversas (*.down.sql) se excluyen."""
    if not DIRECTORIO_MIGRACIONES.is_dir():
        return []
    return sorted(
        ruta for ruta in DIRECTORIO_MIGRACIONES.glob("*.sql")
        if not ruta.name.endswith(".down.sql")
    )


def ejecutar_archivo_sql(engine: Engine, ruta: Path) -> ResultadoArchivo:
    """Ejecuta un archivo .sql completo en su propia transacción."""
    nombre = ruta.relative_to(RAIZ_REPOSITORIO).as_posix()
    try:
        with engine.begin() as conexion:
            conexion.exec_driver_sql(ruta.read_text(encoding="utf-8"))
        return nombre, True, ""
    except Exception as exc:
        detalle = str(getattr(exc, "orig", exc)).strip().splitlines()
        return nombre, False, detalle[0] if detalle else exc.__class__.__name__


def aplicar_migraciones(engine: Engine) -> List[ResultadoArchivo]:
    return [ejecutar_archivo_sql(engine, ruta) for ruta in archivos_de_migracion()]


def sincronizar_esquema(engine: Engine) -> Tuple[List[ResultadoArchivo], Dict[str, List[str]]]:
    """Crea las tablas que falten y, solo si hay columnas ausentes, migra.

    Devuelve (resultado de cada migración ejecutada, columnas que siguen faltando).
    En el caso normal (esquema al día) no ejecuta ninguna migración.
    """
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if not columnas_faltantes(engine):
        return [], {}
    resultados = aplicar_migraciones(engine)
    return resultados, columnas_faltantes(engine)
