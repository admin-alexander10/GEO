"""Utilidades geográficas que no dependen del motor de base de datos."""
from math import asin, cos, radians, sin, sqrt

RADIO_TIERRA_KM = 6371.0088


def distancia_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia de círculo máximo (haversine) entre dos puntos WGS84, en km."""
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = radians(lng2 - lng1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * RADIO_TIERRA_KM * asin(min(1.0, sqrt(a)))
