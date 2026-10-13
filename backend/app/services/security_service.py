import base64
import binascii
import html
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import List, Optional, Tuple

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.exceptions import DomainException, EntityNotFoundException
from app.models.security import SeguridadEvento
from app.models.user import Usuario
from app.schemas.security import (
    AntiTheftAlertRequest,
    AntiTheftAlertResponse,
    SecurityContactResponse,
    SecurityEventItem,
    SecurityEventPhoto,
)

# Tope de evidencias por usuario: evita que una sesión robada o un bucle del
# navegador llene la base o use el servidor para enviar correo en masa.
MAX_EVENTOS_POR_HORA = 10

ETIQUETAS_EVENTO = {
    "ANTI_THEFT": "Modo antirrobo activado",
    "SOS": "SOS enviado",
    "PANICO": "Pánico silencioso activado",
    "LLAMADA_EMERGENCIA": "Llamada a un número de emergencia",
}


class CorreoBloqueado(Exception):
    """El correo de seguridad no se puede cambiar todavía."""

    def __init__(self, hasta: datetime):
        super().__init__("Correo de seguridad bloqueado")
        self.hasta = hasta


class SecurityService:
    """Guarda evidencia antirrobo y avisa por correo al propio titular de la cuenta."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Correo de seguridad del usuario
    # ------------------------------------------------------------------
    @staticmethod
    def servidor_puede_enviar() -> bool:
        # "smtp.tu-proveedor.com" era el valor de ejemplo de .env.example: no es un servidor real.
        host = (settings.SMTP_HOST or "").strip().lower()
        return bool(host) and not host.endswith("tu-proveedor.com")

    def _cuenta(self, usuario: str) -> Usuario:
        cuenta = self.db.query(Usuario).filter(Usuario.usuario == usuario).first()
        if not cuenta:
            raise EntityNotFoundException("Usuario", usuario)
        return cuenta

    @staticmethod
    def _bloqueo_vigente(cuenta: Usuario) -> Optional[datetime]:
        hasta = cuenta.correo_seguridad_bloqueado_hasta
        return hasta if hasta and hasta > datetime.utcnow() else None

    def _respuesta_contacto(self, cuenta: Usuario) -> SecurityContactResponse:
        return SecurityContactResponse(
            correo=cuenta.correo_seguridad,
            servidor_puede_enviar=self.servidor_puede_enviar(),
            # Solo tiene efecto si ya hay un correo que proteger.
            bloqueado_hasta=self._bloqueo_vigente(cuenta) if cuenta.correo_seguridad else None,
        )

    def obtener_contacto(self, usuario: str) -> SecurityContactResponse:
        return self._respuesta_contacto(self._cuenta(usuario))

    def guardar_contacto(self, usuario: str, correo: Optional[str]) -> SecurityContactResponse:
        cuenta = self._cuenta(usuario)
        bloqueo = self._bloqueo_vigente(cuenta)
        # Tras un SOS, pánico o evidencia, el correo que ya estaba guardado no se puede
        # cambiar ni borrar: quien tenga el dispositivo no puede desviar las fotos.
        # Si aún no había ninguno, registrarlo sí está permitido.
        if bloqueo and cuenta.correo_seguridad and correo != cuenta.correo_seguridad:
            raise CorreoBloqueado(bloqueo)
        cuenta.correo_seguridad = correo
        self.db.add(cuenta)
        self.db.commit()
        return self._respuesta_contacto(cuenta)

    # ------------------------------------------------------------------
    # Evidencia antirrobo
    # ------------------------------------------------------------------
    def limite_alcanzado(self, usuario: str) -> bool:
        desde = datetime.utcnow() - timedelta(hours=1)
        recientes = self.db.query(SeguridadEvento).filter(
            SeguridadEvento.usuario == usuario,
            SeguridadEvento.creado_en >= desde,
        ).count()
        return recientes >= MAX_EVENTOS_POR_HORA

    def process_anti_theft_alert(self, usuario: str, payload: AntiTheftAlertRequest) -> AntiTheftAlertResponse:
        foto_limpia, mime = self._normalize_base64_image(payload.foto_base64)
        cuenta = self._cuenta(usuario)
        tiene_ubicacion = payload.latitud is not None and payload.longitud is not None

        event = SeguridadEvento(
            usuario=usuario,
            dispositivo_id=usuario,
            tipo_evento=(
                f"{payload.tipo_evento}:{payload.detalle.strip()}"[:60]
                if payload.detalle and payload.detalle.strip()
                else payload.tipo_evento
            ),
            latitud=float(payload.latitud) if tiene_ubicacion else None,
            longitud=float(payload.longitud) if tiene_ubicacion else None,
            foto_base64=f"data:{mime};base64,{foto_limpia}",
            # Solo el correo que el propio usuario guardó: el destino nunca lo decide la petición.
            correo_destino=cuenta.correo_seguridad,
            email_enviado=False,
            ubicacion=(
                WKTElement(f"POINT({payload.longitud} {payload.latitud})", srid=4326)
                if tiene_ubicacion
                else None
            ),
            creado_en=datetime.utcnow(),
        )
        self.db.add(event)
        # Desde este momento el correo de seguridad queda fijo por un tiempo.
        cuenta.correo_seguridad_bloqueado_hasta = event.creado_en + timedelta(hours=settings.SECURITY_EMAIL_LOCK_HOURS)
        self.db.add(cuenta)
        self.db.commit()
        self.db.refresh(event)

        map_url = self._build_map_url(event.latitud, event.longitud)
        email_enviado, motivo = self._send_security_email(event, map_url)

        event.email_enviado = email_enviado
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        if email_enviado:
            mensaje = f"Evidencia guardada. Se envió un correo a {self._enmascarar(event.correo_destino)}."
        elif motivo == "SIN_CORREO_DE_SEGURIDAD":
            mensaje = "Evidencia guardada. No se envió correo: aún no registras un correo de seguridad."
        elif motivo == "SMTP_NO_CONFIGURADO":
            mensaje = "Evidencia guardada. No se envió correo: el servidor no tiene correo saliente configurado."
        else:
            mensaje = "Evidencia guardada. El correo no pudo enviarse; revísala desde tu cuenta."

        return AntiTheftAlertResponse(
            alerta_id=event.id,
            mensaje=mensaje,
            latitud=event.latitud,
            longitud=event.longitud,
            mapa_url=map_url,
            email_enviado=email_enviado,
            motivo_sin_correo=motivo,
        )

    def listar_eventos(self, usuario: str, limit: int = 10) -> List[SecurityEventItem]:
        eventos = self.db.query(SeguridadEvento).filter(
            SeguridadEvento.usuario == usuario,
        ).order_by(SeguridadEvento.id.desc()).limit(limit).all()
        return [
            SecurityEventItem(
                id=evento.id,
                tipo_evento=evento.tipo_evento,
                latitud=evento.latitud,
                longitud=evento.longitud,
                email_enviado=bool(evento.email_enviado),
                creado_en=evento.creado_en,
            )
            for evento in eventos
        ]

    def obtener_foto(self, usuario: str, evento_id: int) -> SecurityEventPhoto:
        evento = self.db.query(SeguridadEvento).filter(
            SeguridadEvento.id == evento_id,
            SeguridadEvento.usuario == usuario,
        ).first()
        if not evento:
            raise EntityNotFoundException("Evidencia", str(evento_id))
        foto = evento.foto_base64
        if not foto.startswith("data:image/"):
            foto = f"data:image/jpeg;base64,{foto}"  # registros anteriores sin cabecera
        return SecurityEventPhoto(id=evento.id, foto=foto)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_base64_image(data_url: str) -> Tuple[str, str]:
        """Devuelve (base64 sin cabecera, tipo MIME) tras comprobar que es una imagen real."""
        mime = "image/jpeg"
        contenido = (data_url or "").strip()
        if contenido.startswith("data:"):
            cabecera, _, contenido = contenido.partition(",")
            if cabecera.startswith("data:image/png"):
                mime = "image/png"
            elif not cabecera.startswith("data:image/jpeg") and not cabecera.startswith("data:image/jpg"):
                raise DomainException("La evidencia debe ser una imagen JPEG o PNG.", "INVALID_PHOTO")
        try:
            binario = base64.b64decode(contenido, validate=True)
        except (binascii.Error, ValueError):
            raise DomainException("La foto no es una imagen válida.", "INVALID_PHOTO")
        es_jpeg = binario.startswith(b"\xff\xd8\xff")
        es_png = binario.startswith(b"\x89PNG\r\n\x1a\n")
        if not (es_jpeg or es_png):
            raise DomainException("La foto no es una imagen JPEG o PNG.", "INVALID_PHOTO")
        return contenido, "image/png" if es_png else mime

    @staticmethod
    def _build_map_url(latitud: Optional[float], longitud: Optional[float]) -> Optional[str]:
        if latitud is None or longitud is None:
            return None
        return f"https://www.openstreetmap.org/?mlat={latitud}&mlon={longitud}#map=17/{latitud}/{longitud}"

    @staticmethod
    def _enmascarar(correo: Optional[str]) -> str:
        if not correo or "@" not in correo:
            return "tu correo"
        nombre, dominio = correo.split("@", 1)
        return f"{nombre[:1]}***@{dominio}"

    def _send_security_email(self, event: SeguridadEvento, map_url: Optional[str]) -> Tuple[bool, Optional[str]]:
        recipient = event.correo_destino
        if not recipient:
            return False, "SIN_CORREO_DE_SEGURIDAD"
        if not self.servidor_puede_enviar():
            return False, "SMTP_NO_CONFIGURADO"

        try:
            _, _, contenido = event.foto_base64.partition(",")
            image_bytes = base64.b64decode(contenido or event.foto_base64, validate=True)
            image_ext = "png" if event.foto_base64.startswith("data:image/png") else "jpeg"
            # El Perú usa UTC-5 todo el año (no tiene horario de verano).
            hora = (event.creado_en - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M:%S") + " (hora de Perú)"
            ubicacion_texto = (
                f"{event.latitud}, {event.longitud}"
                if event.latitud is not None and event.longitud is not None
                else "No disponible (el dispositivo no entregó ubicación)"
            )

            tipo, _, detalle = (event.tipo_evento or "ANTI_THEFT").partition(":")
            etiqueta = ETIQUETAS_EVENTO.get(tipo, ETIQUETAS_EVENTO["ANTI_THEFT"])
            if tipo == "LLAMADA_EMERGENCIA" and detalle:
                etiqueta = f"Llamada de emergencia al {detalle}"

            msg = EmailMessage()
            msg["Subject"] = f"[GEORESCUE IA] {etiqueta} - evidencia #{event.id}"
            msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
            msg["To"] = recipient
            msg.set_content(
                f"{etiqueta} en tu cuenta de GEORESCUE IA.\n\n"
                f"Usuario: {event.usuario}\n"
                f"Hora: {hora}\n"
                f"Ubicación: {ubicacion_texto}\n"
                + (f"Mapa: {map_url}\n" if map_url else "")
                + "\nLa foto tomada por la cámara del dispositivo va adjunta. "
                "Si no fuiste tú, cambia tu contraseña."
            )

            enlace_mapa = (
                f'<p><a href="{html.escape(map_url, quote=True)}" style="color:#2563eb;">Ver la ubicación en el mapa</a></p>'
                if map_url
                else ""
            )
            cuerpo_html = f"""
            <html>
              <body style="font-family: Arial, sans-serif; color:#0f172a; padding:24px;">
                <h2 style="color:#b91c1c;">GEORESCUE IA: {html.escape(etiqueta)}</h2>
                <p>Se guardó una evidencia en tu cuenta.</p>
                <p><strong>Usuario:</strong> {html.escape(event.usuario or 'Desconocido')}</p>
                <p><strong>Hora:</strong> {html.escape(hora)}</p>
                <p><strong>Ubicación:</strong> {html.escape(ubicacion_texto)}</p>
                {enlace_mapa}
                <p>La foto tomada por la cámara del dispositivo va adjunta. Si no fuiste tú, cambia tu contraseña.</p>
              </body>
            </html>
            """
            msg.add_alternative(cuerpo_html, subtype="html")
            msg.add_attachment(
                image_bytes,
                maintype="image",
                subtype=image_ext,
                filename=f"evidencia_{event.id}.{'png' if image_ext == 'png' else 'jpg'}",
            )

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                smtp.send_message(msg)
            return True, None
        except Exception:
            return False, "ERROR_DE_ENVIO"
