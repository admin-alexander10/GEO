-- Reversa de 20261014_bloqueo_correo_seguridad.sql.
ALTER TABLE usuarios DROP COLUMN IF EXISTS correo_seguridad_bloqueado_hasta;
