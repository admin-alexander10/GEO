from datetime import datetime
from typing import Dict, Any
from app.domain.interfaces.gateways import ICAPGateway

class OASISCAPGateway(ICAPGateway):
    """
    Pasarela de interoperabilidad B2G con el estándar internacional
    OASIS Common Alerting Protocol (CAP v1.2) utilizado por INDECI / SINAGERD / COER.
    """

    def format_as_cap_payload(
        self,
        alerta_id: int,
        tipo_emergencia: str,
        gravedad: int,
        lat: float,
        lng: float,
        descripcion: str,
        origen: str
    ) -> Dict[str, Any]:
        urgencia_map = {
            1: "Minor",
            2: "Moderate",
            3: "Expected",
            4: "Severe",
            5: "Extreme"
        }
        severidad_cap = urgencia_map.get(gravedad, "Unknown")
        now_iso = datetime.utcnow().isoformat() + "Z"

        return {
            "identifier": f"GEORESCUE-PE-{alerta_id}-{int(datetime.utcnow().timestamp())}",
            "sender": "sistema@georescue.ai",
            "sent": now_iso,
            "status": "Actual",
            "msgType": "Alert",
            "scope": "Public",
            "info": {
                "category": "Geo",
                "event": tipo_emergencia,
                "urgency": "Immediate" if gravedad >= 4 else "Expected",
                "severity": severidad_cap,
                "certainty": "Observed" if origen != "MANUAL" else "Likely",
                "eventCode": {
                    "valueName": "SAME",
                    "value": "EQW" if "Sismo" in tipo_emergencia else "SVR"
                },
                "headline": f"Alerta Geoespacial de Rescate Nivel {gravedad} - {tipo_emergencia}",
                "description": descripcion,
                "area": {
                    "areaDesc": "Zona de Impacto Detectada",
                    "circle": f"{lat},{lng},1.5" # Círculo radio 1.5km
                }
            }
        }
