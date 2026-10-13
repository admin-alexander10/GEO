from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text

from app.db.base import Base


class PuntoEmergencia(Base):
    """Punto de atención local (comisaría, compañía de bomberos, centro de salud...).

    Es un directorio público: complementa a los números nacionales 105/116/106,
    nunca los reemplaza. Cada entrada guarda de dónde salió el dato y cuándo se
    verificó, porque un teléfono local desactualizado cuesta tiempo en una emergencia.
    Las coordenadas son columnas numéricas simples: el punto más cercano lo calcula
    el dispositivo del usuario, así su ubicación no viaja al servidor.
    """

    __tablename__ = "directorio_emergencia"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tipo = Column(String(20), nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    # Nombre y distrito sin tildes y en minúsculas: evitan duplicados y permiten buscar
    # igual en cualquier motor ("comisaria" encuentra "Comisaría").
    nombre_clave = Column(String(200), nullable=False, index=True)
    distrito_clave = Column(String(120), nullable=False, default="")
    telefono = Column(String(40), nullable=True)
    direccion = Column(String(300), nullable=True)
    distrito = Column(String(120), nullable=True)
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)
    # True cuando las coordenadas son las del poblado (no las del local exacto):
    # la app lo dice al mostrar la distancia.
    ubicacion_aproximada = Column(Boolean, default=False, nullable=False)
    fuente = Column(Text, nullable=False)
    verificado_en = Column(Date, nullable=False)
    activo = Column(Boolean, default=True, nullable=False, index=True)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    actualizado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
