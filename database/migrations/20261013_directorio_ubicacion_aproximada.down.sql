-- Reversa de 20261013_directorio_ubicacion_aproximada.sql.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM directorio_emergencia WHERE ubicacion_aproximada) THEN
        RAISE EXCEPTION 'No se puede revertir: hay entradas marcadas con ubicación aproximada';
    END IF;
END;
$$;
ALTER TABLE directorio_emergencia DROP COLUMN IF EXISTS ubicacion_aproximada;
