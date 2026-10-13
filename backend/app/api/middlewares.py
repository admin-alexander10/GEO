import time
import logging
from fastapi import Request, FastAPI, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.domain.exceptions import (
    DomainException,
    EntityNotFoundException,
    EntityAlreadyExistsException,
    IdempotencyConflictException,
    InvalidCredentialsException,
    UnauthorizedException,
    ForbiddenException,
    GeospatialValidationException
)

logger = logging.getLogger("georescue.audit")

class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware de auditoría y trazabilidad en tiempo real para llamadas de emergencia."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        method = request.method

        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Resaltar eventos de emergencia en logs
        if "/alertas/" in path or "/coaccion/" in path:
            logger.warning(
                f"[TRAZA TÁCTICA] {method} {path} | Status: {response.status_code} | "
                f"IP: {client_ip} | Tiempo: {duration_ms}ms"
            )
        else:
            logger.info(
                f"[HTTP] {method} {path} | Status: {response.status_code} | Tiempo: {duration_ms}ms"
            )

        return response

def setup_exception_handlers(app: FastAPI):
    """Mapea las excepciones del dominio a respuestas HTTP consistentes."""

    @app.exception_handler(EntityNotFoundException)
    async def not_found_handler(request: Request, exc: EntityNotFoundException):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": True, "codigo": exc.code, "mensaje": exc.message}
        )

    @app.exception_handler(EntityAlreadyExistsException)
    async def already_exists_handler(request: Request, exc: EntityAlreadyExistsException):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": True, "codigo": exc.code, "mensaje": exc.message}
        )

    @app.exception_handler(IdempotencyConflictException)
    async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflictException):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": True, "codigo": exc.code, "mensaje": exc.message}
        )

    @app.exception_handler(InvalidCredentialsException)
    async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsException):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": True, "codigo": exc.code, "mensaje": exc.message}
        )

    @app.exception_handler(UnauthorizedException)
    async def unauthorized_handler(request: Request, exc: UnauthorizedException):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": True, "codigo": exc.code, "mensaje": exc.message}
        )

    @app.exception_handler(ForbiddenException)
    async def forbidden_handler(request: Request, exc: ForbiddenException):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": True, "codigo": exc.code, "mensaje": exc.message}
        )

    @app.exception_handler(DomainException)
    async def domain_handler(request: Request, exc: DomainException):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": True, "codigo": exc.code, "mensaje": exc.message}
        )
