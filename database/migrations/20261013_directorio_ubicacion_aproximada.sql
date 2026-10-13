-- Marca las entradas cuyas coordenadas son las del poblado y no las del local exacto.
-- Migración aditiva; es seguro ejecutarla más de una vez.
ALTER TABLE directorio_emergencia
    ADD COLUMN IF NOT EXISTS ubicacion_aproximada BOOLEAN NOT NULL DEFAULT FALSE;
