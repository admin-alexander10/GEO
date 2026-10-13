"""
Excepciones del dominio de negocio para GEORESCUE IA.
Permite que las capas de servicios y repositorios expresen fallos sin acoplarse a códigos HTTP.
"""

class DomainException(Exception):
    """Excepción base del dominio de negocio."""
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code

class EntityNotFoundException(DomainException):
    """Lanzada cuando un recurso solicitado no existe."""
    def __init__(self, entity_name: str, identifier: str):
        super().__init__(
            message=f"{entity_name} con identificador '{identifier}' no fue encontrado.",
            code="NOT_FOUND"
        )

class EntityAlreadyExistsException(DomainException):
    """Lanzada cuando se intenta crear un recurso duplicado."""
    def __init__(self, entity_name: str, identifier: str):
        super().__init__(
            message=f"{entity_name} '{identifier}' ya está registrado en el sistema.",
            code="ALREADY_EXISTS"
        )


class IdempotencyConflictException(DomainException):
    """A client idempotency key was reused for a different alert payload."""

    def __init__(self):
        super().__init__(
            message="El identificador de alerta ya fue usado con datos diferentes.",
            code="IDEMPOTENCY_CONFLICT",
        )


class InvalidCredentialsException(DomainException):
    """Lanzada cuando las credenciales de acceso son incorrectas."""
    def __init__(self, message: str = "Credenciales de acceso inválidas."):
        super().__init__(message=message, code="INVALID_CREDENTIALS")

class UnauthorizedException(DomainException):
    """Lanzada cuando no se suministra un token válido."""
    def __init__(self, message: str = "Acceso no autorizado al sistema."):
        super().__init__(message=message, code="UNAUTHORIZED")

class ForbiddenException(DomainException):
    """Lanzada cuando el usuario no cuenta con el rol requerido."""
    def __init__(self, message: str = "No cuenta con los permisos necesarios para realizar esta acción."):
        super().__init__(message=message, code="FORBIDDEN")

class GeospatialValidationException(DomainException):
    """Lanzada cuando las coordenadas o polígonos son inválidos."""
    def __init__(self, message: str = "Coordenadas geoespaciales inválidas."):
        super().__init__(message=message, code="INVALID_COORDINATES")
