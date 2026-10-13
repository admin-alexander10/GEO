from typing import Dict, Set

from fastapi import WebSocket


class InstitutionalAlertHub:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}

    def connect(self, institution: str, websocket: WebSocket) -> None:
        self._connections.setdefault(institution, set()).add(websocket)

    def disconnect(self, institution: str, websocket: WebSocket) -> None:
        connections = self._connections.get(institution)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(institution, None)

    async def publish_alert(self, institution: str, event: dict) -> None:
        stale = []
        connections = self._connections.get(institution, set())
        for websocket in tuple(connections):
            try:
                await websocket.send_json(event)
            except Exception:
                stale.append((websocket, connections))
        for websocket, connections in stale:
            connections.discard(websocket)


institutional_alert_hub = InstitutionalAlertHub()


async def notificar_bandejas(instituciones, alerta_id: int, tipo: str = "alert.created") -> None:
    """Avisa a las sesiones conectadas de cada institución que su bandeja cambió.

    Es solo un aviso para refrescar la pantalla: la alerta ya está guardada y
    asignada en la base. Si nadie está conectado no se pierde nada.
    """
    for institucion in instituciones or []:
        await institutional_alert_hub.publish_alert(
            institucion,
            {"type": tipo, "alert_id": alerta_id},
        )
