from enum import Enum

class RolUsuario(str, Enum):
    """Roles de acceso al sistema GEORESCUE IA."""
    CIUDADANO = "Ciudadano"
    CENTRO_COMANDO_B2G = "CentroComandoB2G"
    BRIGADA_CAMPO_B2G = "BrigadaCampoB2G"
    ADMIN = "Admin"

class TipoEmergencia(str, Enum):
    """Clasificación de eventos de emergencia y desastres."""
    SISMO_INERCIAL = "Alerta Sísmica Inercial"
    ROBO_ASALTO_COACCION = "ROBO_ASALTO_COACCION"
    PANIC_SILENCIOSO = "panic_silencioso"
    DESLIZAMIENTO_ALUVION = "Deslizamiento_Aluvion"
    ACCIDENTE_URBANO = "Accidente_Urbano"
    OTRO = "OTRO"

class NivelGravedad(int, Enum):
    """Niveles de severidad conforme a protocolos de protección civil."""
    INFORMATIVO = 1
    MENOR = 2
    MODERADO = 3
    GRAVE = 4
    CATASTROFE = 5

class OrigenAlerta(str, Enum):
    """Mecanismo que disparó la alerta en el dispositivo."""
    MANUAL = "MANUAL"
    AUTOMATICO_INERCIA = "AUTOMATICO_INERCIA"
    COACCION_VOZ = "coaccion_voz"
    PANIC_SILENCIOSO = "panic_silencioso"

class EstadoConfirmacion(str, Enum):
    """Estado de verificación por parte del usuario o sensores."""
    CONFIRMADO = "CONFIRMADO"
    EXPIRADO_INCONSCIENTE = "EXPIRADO_INCONSCIENTE"
    CANCELADO_USUARIO = "CANCELADO_USUARIO"
    EN_EVALUACION = "EN_EVALUACION"

class EstadoDespacho(str, Enum):
    """Estado del recurso de rescate B2G asignado."""
    ASIGNADO = "ASIGNADO"
    EN_RUTA = "EN_RUTA"
    EN_ESCENA = "EN_ESCENA"
    ATENDIDO = "ATENDIDO"
    CANCELADO = "CANCELADO"
