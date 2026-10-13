-- Legacy name-only records remain unconsented until both accounts accept a new link.
ALTER TABLE red_familiar
    ADD COLUMN IF NOT EXISTS familiar_usuario VARCHAR(100),
    ADD COLUMN IF NOT EXISTS consentimiento_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS revocado_en TIMESTAMP,
    ADD COLUMN IF NOT EXISTS revocado_por VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_red_familiar_familiar_usuario
    ON red_familiar(familiar_usuario);

CREATE TABLE IF NOT EXISTS family_invitations (
    id SERIAL PRIMARY KEY,
    invitante_usuario VARCHAR(100) NOT NULL,
    invitado_usuario VARCHAR(100) NOT NULL,
    parentesco VARCHAR(80) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    respondido_en TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_family_invitations_invitado
    ON family_invitations(invitado_usuario, estado);

CREATE TABLE IF NOT EXISTS alert_recipients (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alertas_emergencia(id) ON DELETE RESTRICT,
    recipient_type VARCHAR(20) NOT NULL,
    recipient_username VARCHAR(100) NOT NULL,
    available_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP,
    CONSTRAINT uq_alert_recipient UNIQUE(alert_id, recipient_type, recipient_username)
);
CREATE INDEX IF NOT EXISTS idx_alert_recipients_user
    ON alert_recipients(recipient_type, recipient_username);
