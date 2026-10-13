ALTER TABLE alertas_emergencia
    ADD COLUMN IF NOT EXISTS canal_entrada VARCHAR(20) NOT NULL DEFAULT 'API',
    ADD COLUMN IF NOT EXISTS precision_m INTEGER,
    ADD COLUMN IF NOT EXISTS edad_lectura_s INTEGER,
    ADD COLUMN IF NOT EXISTS es_simulacro BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS telefonos_verificados (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    telefono VARCHAR(20) UNIQUE NOT NULL,
    verificado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
    ultimo_intento_fallido_en TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_telefonos_verificados_usuario
    ON telefonos_verificados(usuario);

CREATE TABLE IF NOT EXISTS phone_otp_challenges (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    telefono VARCHAR(20) NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    salt VARCHAR(32) NOT NULL,
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_en TIMESTAMP NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    consumido_en TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_phone_otp_challenges_lookup
    ON phone_otp_challenges(usuario, telefono, expira_en);

CREATE TABLE IF NOT EXISTS dispositivos_firmantes (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    dispositivo_id VARCHAR(100) NOT NULL,
    secreto_cifrado TEXT NOT NULL,
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revocado_en TIMESTAMP,
    CONSTRAINT uq_dispositivo_firmante UNIQUE(usuario, dispositivo_id)
);
CREATE INDEX IF NOT EXISTS idx_dispositivos_firmantes_usuario
    ON dispositivos_firmantes(usuario);

CREATE TABLE IF NOT EXISTS sms_descartados (
    id SERIAL PRIMARY KEY,
    remitente VARCHAR(40) NOT NULL,
    texto TEXT NOT NULL,
    motivo VARCHAR(40) NOT NULL,
    recibido_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sms_descartados_revision
    ON sms_descartados(motivo, recibido_en DESC);

CREATE TABLE IF NOT EXISTS sms_phone_abuse_counters (
    telefono VARCHAR(40) PRIMARY KEY,
    contador INTEGER NOT NULL DEFAULT 0,
    ultimo_motivo VARCHAR(40) NOT NULL,
    actualizado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sms_outbound_rate_limits (
    telefono VARCHAR(20) PRIMARY KEY,
    ventana_iniciada_en TIMESTAMP NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 0
);
