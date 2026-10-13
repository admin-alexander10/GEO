DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM family_invitations)
       OR EXISTS (SELECT 1 FROM alert_recipients)
       OR EXISTS (
            SELECT 1 FROM red_familiar
            WHERE familiar_usuario IS NOT NULL OR consentimiento_en IS NOT NULL
               OR revocado_en IS NOT NULL OR revocado_por IS NOT NULL
       ) THEN
        RAISE EXCEPTION 'Cannot reverse family consent migration without deleting consent or inbox data';
    END IF;
END;
$$;

DROP TABLE IF EXISTS alert_recipients;
DROP TABLE IF EXISTS family_invitations;
DROP INDEX IF EXISTS idx_red_familiar_familiar_usuario;
ALTER TABLE red_familiar
    DROP COLUMN IF EXISTS familiar_usuario,
    DROP COLUMN IF EXISTS consentimiento_en,
    DROP COLUMN IF EXISTS revocado_en,
    DROP COLUMN IF EXISTS revocado_por;
