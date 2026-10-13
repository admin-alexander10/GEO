-- Additive migration: alert retries become idempotent and state changes auditable.
ALTER TABLE alertas_emergencia
    ADD COLUMN IF NOT EXISTS client_alert_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS estado VARCHAR(40) NOT NULL DEFAULT 'REGISTRADA',
    ADD COLUMN IF NOT EXISTS latitud DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS longitud DOUBLE PRECISION;

CREATE UNIQUE INDEX IF NOT EXISTS uq_alertas_client_alert_id
    ON alertas_emergencia(client_alert_id)
    WHERE client_alert_id IS NOT NULL;

ALTER TABLE alertas_emergencia ALTER COLUMN ubicacion DROP NOT NULL;

CREATE TABLE IF NOT EXISTS alert_state_history (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alertas_emergencia(id) ON DELETE RESTRICT,
    actor VARCHAR(100) NOT NULL,
    from_state VARCHAR(40),
    to_state VARCHAR(40) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_state_history_alert_id ON alert_state_history(alert_id);

CREATE OR REPLACE FUNCTION reject_alert_state_history_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'alert_state_history is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_alert_state_history_immutable ON alert_state_history;
CREATE TRIGGER trg_alert_state_history_immutable
BEFORE UPDATE OR DELETE ON alert_state_history
FOR EACH ROW EXECUTE FUNCTION reject_alert_state_history_mutation();

CREATE TABLE IF NOT EXISTS alert_outbox (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alertas_emergencia(id) ON DELETE RESTRICT,
    event_type VARCHAR(80) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_outbox_due ON alert_outbox(status, available_at);
