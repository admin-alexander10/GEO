-- The pre-migration application schema did not use these fields or tables.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM alertas_emergencia WHERE ubicacion IS NULL) THEN
        RAISE EXCEPTION 'Cannot restore NOT NULL while alerts without location exist';
    END IF;
END;
$$;
ALTER TABLE alertas_emergencia ALTER COLUMN ubicacion SET NOT NULL;
DROP TRIGGER IF EXISTS trg_alert_state_history_immutable ON alert_state_history;
DROP FUNCTION IF EXISTS reject_alert_state_history_mutation();
DROP TABLE IF EXISTS alert_outbox;
DROP TABLE IF EXISTS alert_state_history;
DROP INDEX IF EXISTS uq_alertas_client_alert_id;
ALTER TABLE alertas_emergencia
    DROP COLUMN IF EXISTS client_alert_id,
    DROP COLUMN IF EXISTS estado,
    DROP COLUMN IF EXISTS latitud,
    DROP COLUMN IF EXISTS longitud;
