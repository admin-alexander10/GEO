"""Arranque para Render (plan gratuito, sin consola).

Hace, en orden y de forma repetible:
  1. Completa variables de entorno que Render no puede generar solo.
  2. Prepara la base de datos (PostGIS, esquema inicial, tablas, migraciones),
     reutilizando scripts/preparar_bd.py sin la parte de "crear la base", porque
     Render ya la crea.
  3. Si existe OWNER_PASSWORD, fija la contraseña del propietario de la plataforma
     (en Render el acceso con la clave temporal "admin" no funciona porque no es
     localhost).
  4. Arranca el servidor único (frontend + API) en el puerto que asigna Render.

No modifica ningún archivo del proyecto.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
sys.path.insert(0, str(RAIZ / "scripts"))


def completar_entorno() -> None:
    url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if url:
        os.environ.setdefault("ALLOWED_ORIGINS", url)
        os.environ.setdefault("APP_BASE_URL", url)
    semilla = os.environ.get("DEVICE_KEY_SEED", "")
    if semilla and not os.environ.get("SMS_DEVICE_ENCRYPTION_KEY"):
        # Clave Fernet válida y estable derivada de la semilla.
        os.environ["SMS_DEVICE_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(
            hashlib.sha256(semilla.encode("utf-8")).digest()
        ).decode("ascii")


def preparar_base(intentos: int = 6, espera: int = 10) -> bool:
    import preparar_bd

    preparar_bd.crear_base_si_falta = lambda: None  # Render ya creó la base
    for intento in range(1, intentos + 1):
        try:
            if preparar_bd.main() == 0:
                return True
        except SystemExit as exc:
            print(f"[render] preparar_bd terminó: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[render] Error preparando la base: {exc}")
        if intento < intentos:
            print(f"[render] Reintentando en {espera} s ({intento}/{intentos})...")
            time.sleep(espera)
    return False


def fijar_propietario() -> None:
    clave = os.environ.get("OWNER_PASSWORD", "")
    if not clave:
        print("[render] OWNER_PASSWORD no definida: no se toca la cuenta del propietario.")
        return
    if len(clave) < 10 or clave.lower() == "admin":
        print("[render] OWNER_PASSWORD debe tener al menos 10 caracteres. No se aplicó.")
        return
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.subscription import PlatformAdminAccount as Cuenta

    db = SessionLocal()
    try:
        cuenta = db.query(Cuenta).filter(Cuenta.id == 1).first()
        if cuenta is None:
            cuenta = Cuenta(id=1, password_hash="x", must_change_password=False)
        cuenta.password_hash = hash_password(clave)
        cuenta.must_change_password = False
        db.add(cuenta)
        db.commit()
        print("[render] Contraseña del propietario aplicada.")
    finally:
        db.close()


def main() -> None:
    completar_entorno()
    if not preparar_base():
        print("[render] ATENCIÓN: la base no quedó lista. Revisa los mensajes anteriores.")
    else:
        fijar_propietario()

    import uvicorn

    from servir_todo import app

    puerto = int(os.environ.get("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=puerto, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
