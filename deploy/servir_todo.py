"""Sirve frontend + API en UN solo puerto, para compartir un único enlace de pruebas.

No modifica ningún archivo del proyecto. Uso (desde la raíz del repositorio, con
el entorno virtual activo):

    python deploy/servir_todo.py            # puerto 8080
    python deploy/servir_todo.py 9000       # otro puerto

Luego expón ese puerto con un túnel (cloudflared tunnel --url http://localhost:8080).

Reglas de enrutado:
  - /api/*, /health, /docs, /redoc, /openapi.json   -> backend (HTTP y WebSocket)
  - /  pedido por un navegador (Accept: text/html)  -> frontend (index.html)
  - /  pedido por código (fetch)                    -> backend (el frontend lo usa
                                                      como comprobación de salud)
  - /js/config.js                                   -> versión generada que apunta
                                                      al mismo origen del enlace
  - cualquier otra ruta                             -> archivos del frontend
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from starlette.responses import Response  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from main import app as api_app  # noqa: E402

FRONTEND = RAIZ / "frontend"
RUTAS_API = ("/api/", "/health", "/docs", "/redoc", "/openapi.json")


def _config_js() -> bytes:
    """Copia de frontend/js/config.js con API_HOSTS apuntando al mismo origen."""
    lineas = (FRONTEND / "js" / "config.js").read_text(encoding="utf-8").splitlines()
    salida: list[str] = []
    saltando = False
    for linea in lineas:
        if "API_HOSTS" in linea and "[" in linea:
            salida.append("    API_HOSTS: [window.location.origin],")
            saltando = "]" not in linea
            continue
        if saltando:
            if "]" in linea:
                saltando = False
            continue
        salida.append(linea)
    return ("\n".join(salida) + "\n").encode("utf-8")


class Enrutador:
    def __init__(self) -> None:
        self.estaticos = StaticFiles(directory=str(FRONTEND), html=True)
        self.config = _config_js()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await api_app(scope, receive, send)
            return

        ruta = scope.get("path", "")
        if scope["type"] == "websocket" or ruta.startswith(RUTAS_API):
            await api_app(scope, receive, send)
            return

        if scope["type"] == "http" and ruta == "/js/config.js":
            respuesta = Response(
                self.config,
                media_type="application/javascript",
                headers={"Cache-Control": "no-store"},
            )
            await respuesta(scope, receive, send)
            return

        if scope["type"] == "http" and ruta == "/":
            cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            if "text/html" not in cabeceras.get("accept", ""):
                await api_app(scope, receive, send)
                return

        await self.estaticos(scope, receive, send)


app = Enrutador()

if __name__ == "__main__":
    import uvicorn

    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    uvicorn.run(app, host="127.0.0.1", port=puerto, proxy_headers=True, forwarded_allow_ips="127.0.0.1")
