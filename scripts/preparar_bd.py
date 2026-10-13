"""Prepara o actualiza la base de datos de GEORESCUE IA.

Uso (desde la raíz del repositorio, con el entorno virtual activado):

    python scripts/preparar_bd.py

Lee las credenciales del archivo .env (las mismas que usa el backend) y:

  1. Crea la base de datos si no existe.
  2. Activa la extensión PostGIS.
  3. Si la base está vacía, ejecuta database/init_db.sql.
  4. Crea las tablas que el backend define y que aún no existan.
  5. Ejecuta todas las migraciones de database/migrations/ en orden.
  6. Comprueba que cada tabla tenga las columnas que el backend espera.

Todos los pasos se pueden repetir sin riesgo: las migraciones solo agregan lo
que falta y no borran datos. Los archivos *.down.sql (reversas) no se ejecutan.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.esquema import (  # noqa: E402
    ESQUEMA_INICIAL,
    aplicar_migraciones,
    columnas_faltantes,
    ejecutar_archivo_sql,
)

AYUDA_CONEXION = (
    "[ERROR] PostgreSQL rechazó la conexión. Revisa DB_USER, DB_PASSWORD, "
    "DB_HOST y DB_PORT en el archivo .env y que el servicio esté encendido."
)


def crear_base_si_falta() -> None:
    try:
        conexion = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dbname="postgres",
        )
    except UnicodeDecodeError:
        # En Windows en español psycopg2 no logra decodificar el mensaje de error
        # de PostgreSQL; casi siempre es usuario o contraseña incorrectos.
        raise SystemExit(AYUDA_CONEXION)
    except psycopg2.OperationalError as exc:
        raise SystemExit(f"{AYUDA_CONEXION}\n        Detalle: {str(exc).strip()}")

    conexion.autocommit = True
    try:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.DB_NAME,))
            if cursor.fetchone():
                print(f"[ok] La base '{settings.DB_NAME}' ya existe.")
                return
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.DB_NAME)))
            print(f"[ok] Base '{settings.DB_NAME}' creada.")
    finally:
        conexion.close()


def informar(resultado) -> int:
    nombre, correcto, detalle = resultado
    print(f"[ok] {nombre}" if correcto else f"[ERROR] {nombre}: {detalle}")
    return 0 if correcto else 1


def main() -> int:
    print(f"Servidor: {settings.DB_HOST}:{settings.DB_PORT}  Base: {settings.DB_NAME}  Usuario: {settings.DB_USER}")
    crear_base_si_falta()

    import app.models  # noqa: F401  (registra los modelos)

    engine = create_engine(settings.SQLALCHEMY_DATABASE_URL)
    errores = 0
    try:
        try:
            with engine.begin() as conexion:
                conexion.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
            print("[ok] Extensión PostGIS activa.")
        except Exception as exc:
            print(f"[ERROR] No se pudo activar PostGIS: {str(getattr(exc, 'orig', exc)).strip()}")
            print("        Instálalo con Stack Builder (viene con el instalador de PostgreSQL) y repite.")
            return 1

        base_vacia = "usuarios" not in inspect(engine).get_table_names()
        if base_vacia:
            print("Base vacía: se ejecuta el esquema inicial.")
            errores += informar(ejecutar_archivo_sql(engine, ESQUEMA_INICIAL))

        # Tablas que solo define el backend (planes, suscripciones, instituciones...).
        Base.metadata.create_all(bind=engine)
        print("[ok] Tablas del backend creadas o ya existentes.")

        for resultado in aplicar_migraciones(engine):
            errores += informar(resultado)

        if not base_vacia:
            # En una base antigua los índices de init_db.sql solo se pueden crear
            # después de que las migraciones agregaron las columnas nuevas.
            errores += informar(ejecutar_archivo_sql(engine, ESQUEMA_INICIAL))

        faltantes = columnas_faltantes(engine)
        if faltantes:
            errores += 1
            print("[ERROR] El esquema no coincide con el backend:")
            for tabla, columnas in sorted(faltantes.items()):
                print(f"        {tabla}: falta {', '.join(columnas)}")
        else:
            print("[ok] Todas las tablas tienen las columnas que el backend espera.")
    finally:
        engine.dispose()

    if errores:
        print(f"\nTerminó con {errores} problema(s). Copia este texto y revísalo antes de arrancar el backend.")
        return 1
    print("\nBase de datos lista. Ya puedes arrancar el backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
