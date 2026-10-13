-- Reversa de 20261012_directorio_emergencia.sql. Se niega a borrar un directorio con datos.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM directorio_emergencia) THEN
        RAISE EXCEPTION 'No se puede revertir: el directorio de emergencia tiene entradas';
    END IF;
END;
$$;
DROP TABLE IF EXISTS directorio_emergencia;
