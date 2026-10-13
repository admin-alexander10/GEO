from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.db.base import Base


class SeguridadEvento(Base):
    """Registra eventos de seguridad antirrobo y de protección activa.

    Los datos geoespaciales se almacenan como POINT SRID 4326 para que puedan
    ser consultados y visualizados desde PostGIS en el mapa interno de la app.
    """

    __tablename__ = "eventos_seguridad"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    usuario = Column(String(100), index=True, nullable=True)
    dispositivo_id = Column(String(100), index=True, nullable=True)
    tipo_evento = Column(String(60), default="ANTI_THEFT", index=True, nullable=False)
    # La ubicación es opcional: si el dispositivo no la entrega no se inventa una.
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)
    ubicacion = Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)
    foto_base64 = Column(Text, nullable=False)
    correo_destino = Column(String(255), nullable=True)
    email_enviado = Column(Boolean, default=False, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
