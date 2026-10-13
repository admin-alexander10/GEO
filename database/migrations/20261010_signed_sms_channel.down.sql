DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM telefonos_verificados)
       OR EXISTS (SELECT 1 FROM phone_otp_challenges)
       OR EXISTS (SELECT 1 FROM dispositivos_firmantes)
       OR EXISTS (SELECT 1 FROM sms_descartados)
       OR EXISTS (SELECT 1 FROM sms_phone_abuse_counters)
       OR EXISTS (SELECT 1 FROM sms_outbound_rate_limits)
       OR EXISTS (
            SELECT 1 FROM alertas_emergencia
            WHERE canal_entrada <> 'API'
               OR precision_m IS NOT NULL
               OR edad_lectura_s IS NOT NULL
               OR es_simulacro IS TRUE
       ) THEN
        RAISE EXCEPTION 'Cannot reverse signed SMS migration without losing SMS or alert metadata';
    END IF;
END;
$$;

DROP TABLE IF EXISTS sms_outbound_rate_limits;
DROP TABLE IF EXISTS sms_phone_abuse_counters;
DROP TABLE IF EXISTS sms_descartados;
DROP TABLE IF EXISTS dispositivos_firmantes;
DROP TABLE IF EXISTS phone_otp_challenges;
DROP TABLE IF EXISTS telefonos_verificados;

ALTER TABLE alertas_emergencia
    DROP COLUMN IF EXISTS canal_entrada,
    DROP COLUMN IF EXISTS precision_m,
    DROP COLUMN IF EXISTS edad_lectura_s,
    DROP COLUMN IF EXISTS es_simulacro;
