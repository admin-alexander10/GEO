from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models.sms import (
    DeviceSigningKey,
    DiscardedSMS,
    PhoneOTPChallenge,
    SMSOutboundRateLimit,
    SMSPhoneAbuseCounter,
    VerifiedPhone,
)


class SMSRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_verified_phone(self, phone: str) -> Optional[VerifiedPhone]:
        return self.db.query(VerifiedPhone).filter(
            VerifiedPhone.telefono == phone,
            VerifiedPhone.activo.is_(True),
        ).first()

    def get_user_phone(self, username: str, phone: str) -> Optional[VerifiedPhone]:
        return self.db.query(VerifiedPhone).filter(
            VerifiedPhone.usuario == username,
            VerifiedPhone.telefono == phone,
            VerifiedPhone.activo.is_(True),
        ).first()

    def create_otp_challenge(
        self,
        username: str,
        phone: str,
        code_hash: str,
        salt: str,
        now: datetime,
    ) -> PhoneOTPChallenge:
        challenge = PhoneOTPChallenge(
            usuario=username,
            telefono=phone,
            code_hash=code_hash,
            salt=salt,
            creado_en=now,
            expira_en=now + timedelta(minutes=10),
            intentos=0,
        )
        self.db.add(challenge)
        self.db.commit()
        self.db.refresh(challenge)
        return challenge

    def get_latest_otp_challenge(
        self,
        username: str,
        phone: str,
    ) -> Optional[PhoneOTPChallenge]:
        return self.db.query(PhoneOTPChallenge).filter(
            PhoneOTPChallenge.usuario == username,
            PhoneOTPChallenge.telefono == phone,
            PhoneOTPChallenge.consumido_en.is_(None),
        ).order_by(PhoneOTPChallenge.id.desc()).with_for_update().first()

    def save_challenge(self, challenge: PhoneOTPChallenge) -> None:
        self.db.add(challenge)
        self.db.commit()

    def verify_phone(self, username: str, phone: str, now: datetime) -> VerifiedPhone:
        existing = self.db.query(VerifiedPhone).filter(
            VerifiedPhone.telefono == phone
        ).with_for_update().first()
        if existing and existing.usuario != username:
            raise ValueError("El teléfono ya está asociado a otra cuenta.")
        if existing:
            existing.activo = True
            existing.verificado_en = now
            result = existing
        else:
            result = VerifiedPhone(
                usuario=username,
                telefono=phone,
                verificado_en=now,
                activo=True,
            )
            self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def add_device(self, username: str, device_id: str, encrypted_secret: str) -> DeviceSigningKey:
        existing = self.db.query(DeviceSigningKey).filter(
            DeviceSigningKey.usuario == username,
            DeviceSigningKey.dispositivo_id == device_id,
        ).with_for_update().first()
        if existing:
            raise ValueError("Este ID de dispositivo ya fue registrado; usa un ID nuevo.")
        result = DeviceSigningKey(
            usuario=username,
            dispositivo_id=device_id,
            secreto_cifrado=encrypted_secret,
        )
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def revoke_device(self, username: str, device_id: str, now: datetime) -> bool:
        device = self.db.query(DeviceSigningKey).filter(
            DeviceSigningKey.usuario == username,
            DeviceSigningKey.dispositivo_id == device_id,
            DeviceSigningKey.revocado_en.is_(None),
        ).with_for_update().first()
        if not device:
            return False
        device.revocado_en = now
        self.db.add(device)
        self.db.commit()
        return True

    def get_active_devices(self, username: str) -> Sequence[DeviceSigningKey]:
        return self.db.query(DeviceSigningKey).filter(
            DeviceSigningKey.usuario == username,
            DeviceSigningKey.revocado_en.is_(None),
        ).all()

    def get_alert_phone_owner(self, phone: str) -> Optional[VerifiedPhone]:
        return self.get_verified_phone(phone)

    def record_discard(
        self,
        sender: str,
        text: str,
        reason: str,
        now: datetime,
    ) -> None:
        self.db.add(DiscardedSMS(
            remitente=sender[:40],
            texto=text[:2000],
            motivo=reason[:40],
            recibido_en=now,
        ))
        counter = self.db.query(SMSPhoneAbuseCounter).filter(
            SMSPhoneAbuseCounter.telefono == sender[:40]
        ).with_for_update().first()
        if counter:
            counter.contador += 1
            counter.ultimo_motivo = reason[:40]
            counter.actualizado_en = now
            self.db.add(counter)
        else:
            self.db.add(SMSPhoneAbuseCounter(
                telefono=sender[:40],
                contador=1,
                ultimo_motivo=reason[:40],
                actualizado_en=now,
            ))
        self.db.commit()

    def list_discarded(self, limit: int = 100) -> list[DiscardedSMS]:
        return self.db.query(DiscardedSMS).order_by(
            DiscardedSMS.recibido_en.desc()
        ).limit(limit).all()

    def reserve_outbound_slot(
        self,
        phone: str,
        now: datetime,
        limit: int,
        window_seconds: int,
    ) -> bool:
        slot = self.db.query(SMSOutboundRateLimit).filter(
            SMSOutboundRateLimit.telefono == phone
        ).with_for_update().first()
        if slot is None:
            slot = SMSOutboundRateLimit(
                telefono=phone,
                ventana_iniciada_en=now,
                cantidad=0,
            )
            self.db.add(slot)
            self.db.flush()
        elif (now - slot.ventana_iniciada_en).total_seconds() >= window_seconds:
            slot.ventana_iniciada_en = now
            slot.cantidad = 0
        if slot.cantidad >= limit:
            self.db.rollback()
            return False
        slot.cantidad += 1
        self.db.add(slot)
        self.db.commit()
        return True
