-- Migración aditiva. Es seguro ejecutarla más de una vez.
-- Requiere que el backend haya creado antes la tabla institution_accounts
-- (scripts/preparar_bd.py lo hace en el orden correcto).

-- 1. Cobertura geográfica validada por el propietario (centro + radio).
--    Sin coverage_validated_at la institución no recibe alertas automáticas.
ALTER TABLE institution_accounts
    ADD COLUMN IF NOT EXISTS coverage_lat DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS coverage_lng DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS coverage_radius_km DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS coverage_evidence TEXT,
    ADD COLUMN IF NOT EXISTS coverage_validated_by VARCHAR(120),
    ADD COLUMN IF NOT EXISTS coverage_validated_at TIMESTAMP;

-- 2. Correo de seguridad del usuario para el módulo antirrobo.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS correo_seguridad VARCHAR(255);

-- 3. El evento antirrobo ya no exige ubicación: si el dispositivo no la da,
--    se guarda sin coordenadas en lugar de inventar un punto.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'eventos_seguridad') THEN
        ALTER TABLE eventos_seguridad ALTER COLUMN latitud DROP NOT NULL;
        ALTER TABLE eventos_seguridad ALTER COLUMN longitud DROP NOT NULL;
        ALTER TABLE eventos_seguridad ALTER COLUMN ubicacion DROP NOT NULL;
    END IF;
END $$;
