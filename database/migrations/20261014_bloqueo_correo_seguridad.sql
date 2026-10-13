-- Bloqueo temporal del correo de seguridad tras un SOS, pánico o evidencia.
-- Migración aditiva; es seguro ejecutarla más de una vez.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS correo_seguridad_bloqueado_hasta TIMESTAMP;
