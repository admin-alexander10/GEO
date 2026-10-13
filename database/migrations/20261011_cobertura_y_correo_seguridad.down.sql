-- Reversa de 20261011_cobertura_y_correo_seguridad.sql.
-- Se niega a ejecutarse si borraría datos ya registrados.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM institution_accounts WHERE coverage_validated_at IS NOT NULL)
       OR EXISTS (SELECT 1 FROM usuarios WHERE correo_seguridad IS NOT NULL)
       OR EXISTS (SELECT 1 FROM eventos_seguridad WHERE ubicacion IS NULL) THEN
        RAISE EXCEPTION 'No se puede revertir: hay coberturas validadas, correos de seguridad o eventos sin ubicación';
    END IF;
END;
$$;

ALTER TABLE eventos_seguridad ALTER COLUMN ubicacion SET NOT NULL;
ALTER TABLE eventos_seguridad ALTER COLUMN longitud SET NOT NULL;
ALTER TABLE eventos_seguridad ALTER COLUMN latitud SET NOT NULL;
ALTER TABLE usuarios DROP COLUMN IF EXISTS correo_seguridad;
ALTER TABLE institution_accounts
    DROP COLUMN IF EXISTS coverage_lat,
    DROP COLUMN IF EXISTS coverage_lng,
    DROP COLUMN IF EXISTS coverage_radius_km,
    DROP COLUMN IF EXISTS coverage_evidence,
    DROP COLUMN IF EXISTS coverage_validated_by,
    DROP COLUMN IF EXISTS coverage_validated_at;
